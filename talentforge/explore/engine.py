"""探索引擎（M7 spec §3）：资产盘点（纯数据）+ 市场统计 + 快照生成（LLM 一次深推）。

人驱动探索（"我根据已有经历/成果能去哪"），区别于全部岗位驱动链路。
快照失败软降级返回 ([], 错误信息)，绝不 500（同内容探针约定）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter

from talentforge.domain.direction import DirectionCard, EvidenceRef
from talentforge.domain.job import Job
from talentforge.domain.profile import Profile, SalaryRange
from talentforge.domain.work import WorkArtifact
from talentforge.llm.client import LLMClient
from talentforge.llm.json_utils import extract_json

logger = logging.getLogger(__name__)

# prompt-cache 约定（同 CONTENT_PROBE_SYSTEM_PROMPT）：system 为模块级静态
# 常量、零变量；资产盘点与市场统计全在 user message。
EXPLORE_SNAPSHOT_SYSTEM_PROMPT = (
    "你是职业方向探索器。用户消息给出其资产盘点（基本信息/技能簇/强信号/行为兴趣/"
    "八格摘要/硬边界）与国内岗位市场统计，你的任务是从这些既有资产出发向可能性"
    "空间搜索，输出 3-5 张方向卡。只输出一个 JSON 对象，不要输出其他文字。格式："
    '{"directions": [方向卡, ...]}。每张方向卡的字段：scope（track=赛道：这堆资产'
    "能干什么｜lifestyle=活法：同赛道选哪种组织形态｜field=行业：换哪张桌子打）、"
    "title（方向名，如「边缘 AI 部署」）、why_you（证据链数组，每条 "
    "{kind, ref, text}，kind 取 work|profile|behavior|dialogue）、"
    "market_evidence（市场验证）、data_backed（布尔）、distance（差多远，说人话）、"
    "first_step（第一步做什么）、constraint_check（八格/硬边界碰撞提示字符串数组）、"
    "confidence（0 到 1 的小数）。硬性要求：三个口径各至少 1 张卡；why_you 每条"
    "证据必须引用资产清单中条目的原文（kind=work 引用强信号作品、kind=profile 引用"
    "画像/八格、kind=behavior 引用行为兴趣），禁止编造用户没有的资产；"
    "market_evidence 能被岗位统计验证的给关键词/岗位量并设 data_backed=true，"
    "面向海外或统计不可达的推理方向必须设 data_backed=false，在 market_evidence "
    "中注明「推理·置信度X」并下调 confidence；constraint_check 必须逐卡对照硬边界"
    "（deal_breakers/exploitation_redlines）与八格摘要（现金缓冲/城市约束等），"
    "指出真实碰撞（如「竞业硬边界 × 该形态冲突」），无碰撞给空数组。所有文案用中文。"
)

_SCOPES: frozenset[str] = frozenset({"track", "lifestyle", "field"})

# 截断/上限常量（防 LLM 失控输出撑爆存储与前端）
_LANG_TOP = 5            # 技能簇语言数
_CLAIM_TEXT_MAX = 120    # 主张文本截断
_INTEREST_TOP = 10       # 行为兴趣条数上限
_GRID_TEXT_MAX = 120     # 八格单格截断
_TITLE_MAX = 60
_MARKET_MAX = 300
_FIELD_MAX = 200         # distance/first_step/证据 text
_REF_MAX = 120
_CONSTRAINT_MAX = 120
_MAX_CONSTRAINTS = 8
_MAX_EVIDENCE = 8
_KEYWORD_TOP = 20        # 市场关键词条数
_MIN_TOKEN_LEN = 2       # 2 字以上词
_TOKEN_STRIP = "()（）[]【】{}《》<>«»,，、;；:：.。!！?？·-—_|*#"

_STANCE_ZH = {"accept": "可接受", "negotiable": "可协商", "never": "绝不"}

# 分词粗统计：按空格/斜杠拆（Boss title 语义里斜杠是并列分隔符）
_TOKEN_SPLIT_RE = re.compile(r"[\s/\\]+")


def _truncate(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def card_id_for(title: str) -> str:
    """方向卡标题 → 稳定 card_id（dir-{sha1[:12]}，同 claim_id_for 模式）。"""
    digest = hashlib.sha1(str(title).encode("utf-8")).hexdigest()[:12]
    return f"dir-{digest}"


def _salary_text(wage: SalaryRange | None) -> str:
    """最低可接受薪资 → 展示文本（万/年，两端缺失返回空串；域内轻量实现不依赖 api 层）。"""
    if wage is None:
        return ""
    lo, hi = wage.min_annual, wage.max_annual
    if lo is None and hi is None:
        return ""

    def _wan(value: int) -> str:
        return f"{value / 10000:g}"

    if lo is not None and hi is not None:
        return f"{_wan(lo)}-{_wan(hi)}万/年"
    if lo is not None:
        return f"≥{_wan(lo)}万/年"
    if hi is not None:
        return f"≤{_wan(hi)}万/年"
    return ""


def build_asset_brief(profile: Profile, artifacts: list[WorkArtifact]) -> dict:
    """资产盘点（纯数据无 LLM，spec §3.1）：技能簇 + 强信号 + 行为兴趣 + 八格 + 硬边界。

    深谈模式先展示给用户纠错（D23 防线 c 同构）；空输入不炸，字段齐全值为空。
    """
    lang_counts: Counter[str] = Counter()
    for artifact in artifacts:
        lang = str(artifact.facts.get("language") or "").strip()
        if lang:
            lang_counts[lang] += 1
    skill_clusters = [
        {"language": lang, "repos": count}
        for lang, count in lang_counts.most_common(_LANG_TOP)
    ]

    strong_signals: list[str] = []
    for artifact in artifacts:
        if artifact.grade != "strong":
            continue
        facts = artifact.facts or {}
        parts = [str(facts.get("language") or "").strip()]
        commits = facts.get("commits")
        if commits:
            parts.append(f"{commits} commits")
        inner = "，".join(p for p in parts if p)
        entry = f"{artifact.title}（{inner}）" if inner else artifact.title
        strong_signals.append(f"[{artifact.platform}] {entry}")
    strong_signals.extend(
        claim.text[:_CLAIM_TEXT_MAX]
        for claim in profile.narrative_claims
        if claim.state == "active"
    )

    behavior_interests = [
        claim.text[:_CLAIM_TEXT_MAX]
        for claim in profile.narrative_claims
        if claim.state == "trial"
    ][:_INTEREST_TOP]

    sp = profile.structural_position
    structural_summary = {
        "cash_buffer": _truncate(sp.cash_buffer, _GRID_TEXT_MAX),
        "stage": _truncate(sp.stage, _GRID_TEXT_MAX),
        "city_constraints": [_truncate(c, _GRID_TEXT_MAX) for c in sp.city_constraints],
        "family_duty": _truncate(sp.family_duty, _GRID_TEXT_MAX),
        "support_network": [
            _truncate(f"{s.kind}：{s.note}", _GRID_TEXT_MAX) for s in sp.support_network
        ],
        "economic_independence": _truncate(sp.economic_independence, _GRID_TEXT_MAX),
        "family_payback": "是" if sp.family_payback else "否",
        "reservation_wage": _salary_text(sp.reservation_wage),
        "material_conditions": _truncate(sp.material_conditions, _GRID_TEXT_MAX),
        "social_relations": _truncate(sp.social_relations, _GRID_TEXT_MAX),
    }
    hard_boundaries = {
        "deal_breakers": [_truncate(d, _GRID_TEXT_MAX) for d in profile.deal_breakers],
        "exploitation_redlines": [
            _truncate(f"{r.kind}（{_STANCE_ZH.get(r.stance, r.stance)}）", _GRID_TEXT_MAX)
            for r in sp.exploitation_redlines
        ],
    }
    return {
        "basics": {
            "years_experience": profile.years_experience,
            "skills": list(profile.skills),
            "desired_roles": list(profile.desired_roles),
        },
        "skill_clusters": skill_clusters,
        "strong_signals": strong_signals,
        "behavior_interests": behavior_interests,
        "structural_summary": structural_summary,
        "hard_boundaries": hard_boundaries,
    }


def build_market_stats(jobs: list[Job]) -> dict:
    """岗位库统计（spec §3.2）：title 关键词频率粗统计 + 总岗数，给 LLM 国内市场感知。"""
    counter: Counter[str] = Counter()
    for job in jobs:
        for raw in _TOKEN_SPLIT_RE.split(job.title or ""):
            token = raw.strip(_TOKEN_STRIP)
            if len(token) >= _MIN_TOKEN_LEN:
                counter[token] += 1
    return {
        "total_jobs": len(jobs),
        "title_keywords": [
            {"keyword": keyword, "count": count}
            for keyword, count in counter.most_common(_KEYWORD_TOP)
        ],
    }


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() == "true"


def _parse_evidence(item: object) -> EvidenceRef | None:
    """单条证据容错解析：非 dict / text 缺失 → None（跳过该条不毁整卡）。"""
    if not isinstance(item, dict):
        return None
    text = _truncate(item.get("text"), _FIELD_MAX)
    if not text:
        return None
    return EvidenceRef(
        kind=_truncate(item.get("kind"), 40) or "profile",
        ref=_truncate(item.get("ref"), _REF_MAX),
        text=text,
    )


def _parse_card(item: object) -> DirectionCard | None:
    """LLM 单卡输出 → DirectionCard；scope 非法/标题缺失返回 None（跳过该卡不毁整批）。

    容错：confidence clamp 0-1（解析失败回 0.5）；截断 title 60 / market_evidence
    300 / distance 200 / first_step 200 / 单条 constraint 120 / 证据 text 200。
    """
    if not isinstance(item, dict):
        return None
    scope = item.get("scope")
    if scope not in _SCOPES:
        return None
    title = _truncate(item.get("title"), _TITLE_MAX)
    if not title:
        return None

    why_you: list[EvidenceRef] = []
    raw_why = item.get("why_you")
    if isinstance(raw_why, list):
        for entry in raw_why[:_MAX_EVIDENCE]:
            ref = _parse_evidence(entry)
            if ref is not None:
                why_you.append(ref)

    constraints: list[str] = []
    raw_constraints = item.get("constraint_check")
    if isinstance(raw_constraints, list):
        constraints = [
            c
            for c in (
                _truncate(x, _CONSTRAINT_MAX)
                for x in raw_constraints[:_MAX_CONSTRAINTS]
            )
            if c
        ]

    try:
        confidence = min(1.0, max(0.0, float(item.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    return DirectionCard(
        card_id=card_id_for(title),
        scope=scope,  # type: ignore[arg-type]  # 已过 _SCOPES 枚举校验
        title=title,
        why_you=why_you,
        market_evidence=_truncate(item.get("market_evidence"), _MARKET_MAX),
        data_backed=_coerce_bool(item.get("data_backed")),
        distance=_truncate(item.get("distance"), _FIELD_MAX),
        first_step=_truncate(item.get("first_step"), _FIELD_MAX),
        constraint_check=constraints,
        confidence=confidence,
        created_from=_truncate(item.get("created_from"), _TITLE_MAX),
    )


async def generate_snapshot(
    profile: Profile,
    artifacts: list[WorkArtifact],
    jobs: list[Job],
    llm: LLMClient,
) -> tuple[list[DirectionCard], str]:
    """快照生成（spec §3.2）：资产盘点 + 市场统计拼 user message → LLM 一次深推。

    返回 (cards, error_msg)：解析容错（directions 非 list → ([], "解析失败…")；
    单卡校验失败跳过不毁整批；LLM/解析异常 → ([], 错误信息)），绝不抛出。
    """
    brief = build_asset_brief(profile, artifacts)
    stats = build_market_stats(jobs)
    user = (
        "资产盘点：\n"
        + json.dumps(brief, ensure_ascii=False)
        + "\n\n国内岗位市场统计：\n"
        + json.dumps(stats, ensure_ascii=False)
        + "\n\n请基于以上资产生成方向卡快照。"
    )
    try:
        raw = await llm.chat(EXPLORE_SNAPSHOT_SYSTEM_PROMPT, user)
        data = extract_json(raw)
    except Exception as exc:  # LLM 未配置/网络/解析失败：软降级，不 500
        logger.warning("方向快照生成失败: %s", exc)
        return [], f"快照生成失败：{exc}"

    directions = data.get("directions")
    if not isinstance(directions, list):
        logger.warning("方向快照 directions 形状异常: %r", type(directions))
        return [], "解析失败：directions 应为列表"

    cards: list[DirectionCard] = []
    for item in directions:
        card = _parse_card(item)
        if card is not None:
            cards.append(card)
    if directions and not cards:
        return [], f"解析失败：{len(directions)} 张方向卡全部无效"
    return cards, ""
