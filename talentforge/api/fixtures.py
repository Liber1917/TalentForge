"""M3 离线假数据：卡片契约 JSON 的演示样例（spec-m3-web §1/§5）。

前端开发期不依赖真实 LLM/抓取，直接消费这些 fixture 驱动全部卡片渲染。
数据贴近真实场景：信息类转码同学 / 后端方向 / 深圳 / 996 / 竞业等。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from talentforge.api.schemas import (
    ChatTurn,
    ClaimCard,
    ClaimSourceRef,
    DecisionCard,
    EvidenceRef,
    JobRef,
    ReflectivePrompt,
    RiskHit,
    RiskNote,
)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROFILE_PATH = _PACKAGE_ROOT / "docs" / "demo" / "profile.json"

_BASE = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)


def _at(index: int) -> datetime:
    """第 index 轮对话的固定时间戳（每轮 +1 分钟）。"""
    return _BASE + timedelta(minutes=index)


def _iso(dt: datetime) -> str:
    """datetime → ISO 字符串（证据来源 at 字段用）。"""
    return dt.isoformat()


def get_fixture_chat() -> list[ChatTurn]:
    """5 条离线对话：覆盖 DecisionCard×2 / ClaimCard×1 / RiskNote×1 / ReflectivePrompt×1。

    叙事：用户问深圳后端岗 → 助手回两张决策卡（hold+skip）；
    用户反问（996/竞业 + 自述系统设计积累）→ 助手回风险提示卡 + 画像主张卡 + 反思提问卡。
    """
    risk_why_996 = (
        "996 意味着劳动时间被系统性延长——超出法定工时的部分通常不支付对价，"
        "长期会压缩你的再生产时间（睡眠/学习/社交）。这不是道德判断，"
        "是你需要知情权衡的事实。"
    )
    return [
        ChatTurn(
            role="user",
            text="帮我看看深圳的后端岗位？最近在找机会，想听听你的判断。",
            at=_at(0),
        ),
        ChatTurn(
            role="assistant",
            text="给你看了两份深圳后端岗，先各给一个结论：一家先观望，一家直接排除。",
            cards=[
                DecisionCard(
                    job=JobRef(
                        title="Python 后端工程师",
                        company="星辰科技",
                        url="https://www.zhipin.com/job_detail/python_1001.html",
                        salary="25-50K·16薪",
                    ),
                    verdict="hold",
                    reason=(
                        "市场契合高，但 JD 明确标注 996，与你上次划的硬边界冲突——"
                        "先观望，看能否谈到工时与对价。"
                    ),
                    risk_hits=[RiskHit(key="996", label="996 工作制")],
                    evidence=[
                        EvidenceRef(
                            kind="jd", ref="python_1001.html", text="工作时间为 996 工作制"
                        ),
                        EvidenceRef(kind="dialogue", ref="turn-1", text="用户偏好深圳后端岗"),
                    ],
                ),
                DecisionCard(
                    job=JobRef(
                        title="高级后端开发（Java）",
                        company="云帆信息",
                        url="https://www.zhipin.com/job_detail/java_1002.html",
                        salary="15-25K",
                    ),
                    verdict="skip",
                    reason="薪资低于你的保留工资，且含竞业限制条款，与硬边界直接冲突。",
                    risk_hits=[RiskHit(key="竞业限制", label="竞业限制条款")],
                    evidence=[
                        EvidenceRef(
                            kind="jd", ref="java_1002.html", text="含竞业限制条款，范围覆盖同业"
                        ),
                        EvidenceRef(
                            kind="system", ref="deal-breaker", text="用户 deal_breakers 含竞业限制"
                        ),
                    ],
                ),
            ],
            at=_at(1),
        ),
        ChatTurn(
            role="user",
            text=(
                "星辰科技标着 996，云帆还有竞业，我都挺犹豫。"
                "其实我在分布式系统这块积累挺深，最近在准备系统设计面试。"
            ),
            at=_at(2),
        ),
        ChatTurn(
            role="assistant",
            text=(
                "你的犹豫有依据，风险先单独拆开讲；另外把'系统设计积累'记成一条待验证主张，"
                "后续用行为验证。"
            ),
            cards=[
                RiskNote(key="996", label="996 工作制", why=risk_why_996),
                ClaimCard(
                    claim_id="claim-demo-sysdes-01",
                    text="用户对分布式系统/系统设计有深度积累，正在系统化准备系统设计面试",
                    state="trial",
                    evidence_count=0,
                    sources=[ClaimSourceRef(kind="dialogue", ref="turn-3", at=_iso(_at(2)))],
                    confidence=0.75,
                ),
                ReflectivePrompt(
                    question="你上次说 996 是硬边界，现在这份岗位明确标着 996——怎么权衡？"
                ),
            ],
            at=_at(3),
        ),
        ChatTurn(
            role="user",
            text="嗯，996 如果给足对价和时间弹性我可以谈，但竞业限制是硬边界。",
            at=_at(4),
        ),
    ]


def get_fixture_jobs() -> list[dict]:
    """8 个深圳后端岗位：覆盖 apply/hold/skip 三态 + 含/不含风险。

    每个岗位为 spec §1 DecisionCard.job 的扩展（补 location/verdict/reason/
    risk_hits/gap/remediation），供工作台列表/详情渲染。
    """
    return [
        {
            "title": "数据平台后端工程师",
            "company": "观澜数据",
            "location": "深圳·福田",
            "salary": "30-45K·14薪",
            "url": "https://www.zhipin.com/job_detail/data_1006.html",
            "verdict": "apply",
            "reason": "成长契合高（流计算方向补强），薪资覆盖保留工资，双休弹性工时。",
            "risk_hits": [],
            "gap": ["Flink 流处理"],
            "remediation": ["搭一个 Flink 词频 demo 上简历", "面试前补两道流计算设计题"],
        },
        {
            "title": "后端开发工程师（Python/Go）",
            "company": "睿达网络",
            "location": "深圳·南山",
            "salary": "28-45K·15薪",
            "url": "https://www.zhipin.com/job_detail/ruida_1010.html",
            "verdict": "apply",
            "reason": "技术栈双覆盖、分布式业务对口，仅需核实工时与加班口径。",
            "risk_hits": [{"key": "弹性工作制需核实", "label": "弹性工作制（需核实）"}],
            "gap": ["流量治理"],
            "remediation": ["整理一个限流/熔断实践案例"],
        },
        {
            "title": "Python 后端工程师",
            "company": "星辰科技",
            "location": "深圳·南山",
            "salary": "25-50K·16薪",
            "url": "https://www.zhipin.com/job_detail/python_1001.html",
            "verdict": "hold",
            "reason": "市场契合高，但 JD 明确标注 996，与硬边界冲突——先观望对价能否谈拢。",
            "risk_hits": [{"key": "996", "label": "996 工作制"}],
            "gap": ["K8s 容器编排", "高并发压测"],
            "remediation": ["若谈薪资需先确认加班口径", "个人项目补 K8s 部署实践"],
        },
        {
            "title": "Go 后端开发",
            "company": "海天互娱",
            "location": "深圳·宝安",
            "salary": "20-30K·13薪",
            "url": "https://www.zhipin.com/job_detail/go_1007.html",
            "verdict": "hold",
            "reason": "IM 场景能补高并发经验，但单休安排与偏好冲突，需确认调休补偿。",
            "risk_hits": [{"key": "单休", "label": "单休工作制"}],
            "gap": ["WebSocket 长连接", "消息队列"],
            "remediation": ["补一个 IM 聊天 demo 的实时链路", "确认单休是否换算加班费"],
        },
        {
            "title": "高级后端开发（Java）",
            "company": "云帆信息",
            "location": "深圳·南山",
            "salary": "15-25K",
            "url": "https://www.zhipin.com/job_detail/java_1002.html",
            "verdict": "skip",
            "reason": "薪资低于保留工资，且含竞业限制条款，与硬边界直接冲突。",
            "risk_hits": [{"key": "竞业限制", "label": "竞业限制条款"}],
            "gap": ["Java 交易系统经验"],
            "remediation": ["竞业为硬边界，暂缓投入"],
        },
        {
            "title": "Golang 基础架构工程师",
            "company": "星环科技",
            "location": "深圳·南山",
            "salary": "30-45K·14薪",
            "url": "https://www.zhipin.com/job_detail/golang_1004.html",
            "verdict": "skip",
            "reason": "明确 996 + 无偿加班，两处硬边界直接命中，薪资不补偿工时。",
            "risk_hits": [
                {"key": "996", "label": "996 工作制"},
                {"key": "无偿加班", "label": "无偿加班"},
            ],
            "gap": ["K8s 源码级理解"],
            "remediation": ["决策已跳过，不建议投入时间"],
        },
        {
            "title": "后端研发（量化中后台）",
            "company": "方舟金融",
            "location": "深圳·福田",
            "salary": "35-60K·16薪",
            "url": "https://www.zhipin.com/job_detail/finance_1008.html",
            "verdict": "skip",
            "reason": "薪资诱人但含竞业限制条款，与把竞业当硬边界的立场冲突。",
            "risk_hits": [{"key": "竞业限制", "label": "竞业限制条款"}],
            "gap": ["量化领域知识"],
            "remediation": ["竞业为硬边界，暂缓投入"],
        },
        {
            "title": "Java 后端工程师（外包驻场）",
            "company": "微光教育",
            "location": "深圳·龙华",
            "salary": "12-18K",
            "url": "https://www.zhipin.com/job_detail/outsource_1009.html",
            "verdict": "skip",
            "reason": "无社保 + 加班费模糊，法定义务缺失与低薪双重问题。",
            "risk_hits": [
                {"key": "无社保", "label": "无社会保险"},
                {"key": "加班费模糊", "label": "加班费规则模糊"},
            ],
            "gap": ["——"],
            "remediation": ["决策已跳过，不符合底线"],
        },
    ]


def _claim_dict(source: dict, claim_id: str, at: datetime) -> dict:
    """把主张 dict 归一化为 ClaimCard 契约形状（补 claim_id + 来源 at）。"""
    raw_sources = source.get("sources") or []
    if not isinstance(raw_sources, list):
        raw_sources = []
    sources = [
        {**s, "at": s.get("at") or _iso(at)}
        for s in raw_sources
        if isinstance(s, dict)
    ]
    return {
        "claim_id": claim_id,
        "text": str(source.get("text", "")),
        "state": str(source.get("state", "trial")),
        "evidence_count": int(source.get("evidence_count", 0)),
        "confidence": float(source.get("confidence", 0.5)),
        "sources": sources,
    }


def _fill(target: dict, key: str, default: object) -> None:
    """仅当缺失/为空时补默认值（保留文件里已填的内容）。"""
    value = target.get(key)
    if value in (None, "", [], {}, False):
        target[key] = default


_DEFAULT_PREFS: dict[str, dict[str, object]] = {
    "salary": {"attribute": "salary", "ordering": ["40万以上", "30-40万", "20-30万"]},
    "work_mode": {"attribute": "work_mode", "ordering": ["弹性工时", "标准双休", "大小周"]},
    "location": {"attribute": "location", "ordering": ["深圳南山", "深圳福田", "深圳全城"]},
    "company_type": {"attribute": "company_type", "ordering": ["中厂", "大厂", "创业公司"]},
    "tech_stack": {"attribute": "tech_stack", "ordering": ["Python", "Go", "Java"]},
}


def get_fixture_profile(profile_path: str | Path | None = None) -> dict:
    """从 docs/demo/profile.json 读入并补全画像（前端画像面板的离线样例）。

    补全范围：三轨齐备（narrative / utility_preferences / structural_position 八格）、
    narrative_claims 含 trial（待定池 3 条）+ active（1 条，模拟用户已确认）。
    """
    path = Path(profile_path) if profile_path is not None else DEFAULT_PROFILE_PATH
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    claims = data.get("narrative_claims") or []
    trial = [c for c in claims if isinstance(c, dict) and c.get("state") == "trial"]

    pool = [_claim_dict(c, f"claim-demo-{i + 1:02d}", _at(4)) for i, c in enumerate(trial[:3])]

    active_raw: dict[str, Any] = trial[3] if len(trial) > 3 else {
        "text": "用户把 996 视为硬边界，除非给足对价与时间弹性否则不投",
        "state": "trial",
        "evidence_count": 0,
        "confidence": 0.9,
        "sources": [{"kind": "dialogue", "ref": "demo-chat-confirm"}],
    }
    active = _claim_dict(active_raw, "claim-demo-active-01", _at(4))
    active["state"] = "active"
    active["evidence_count"] = int(active_raw.get("evidence_count", 0)) + 1
    active["sources"].append({"kind": "dialogue", "ref": "demo-chat-confirm", "at": _iso(_at(4))})

    narrative = dict(data.get("narrative") or {})
    _fill(narrative, "identity", "深耕后端基础设施的工程师")
    _fill(narrative, "values", ["技术深度", "工作生活平衡", "长期成长"])
    _fill(narrative, "deep_drives", ["系统设计深度"])

    prefs = dict(data.get("utility_preferences") or {})
    for attr, pref in _DEFAULT_PREFS.items():
        if attr not in prefs:
            prefs[attr] = pref

    sp = dict(data.get("structural_position") or {})
    _fill(sp, "cash_buffer", "约6个月")
    _fill(sp, "stage", "3 年经验，处于中期跃迁阶段，计划 6-12 个月内完成一次关键跳槽")
    _fill(sp, "city_constraints", ["深圳", "珠三角"])
    _fill(sp, "family_duty", "暂无重大家庭负担，可接受跨城通勤")
    _fill(sp, "support_network", [
        {"kind": "前同事", "note": "2 名前同事在内推圈，可提供内推"},
        {"kind": "导师", "note": "前组长可作为背调联系人"},
    ])
    _fill(sp, "economic_independence", "经济独立，无重大负债，月度盈余约 4k")
    _fill(sp, "reservation_wage", {"min_annual": 300000, "max_annual": 350000, "currency": "CNY"})
    _fill(sp, "exploitation_redlines", [
        {"kind": "996", "stance": "never"},
        {"kind": "竞业限制", "stance": "never"},
        {"kind": "无偿加班", "stance": "never"},
    ])
    _fill(sp, "reproduction_costs", {
        "housing": "月租 3500，约占收入 20%",
        "commute": "单程 40 分钟",
        "food": "公司周边餐饮日均约 60",
        "skill_half_life_years": 2.0,
    })
    _fill(sp, "mobility", {"dare_bare_quit": True, "note": "6 个月现金缓冲，敢裸辞但更想骑驴找马"})

    profile: dict[str, Any] = {
        **data,
        "narrative": narrative,
        "utility_preferences": prefs,
        "structural_position": sp,
        "narrative_claims": pool + [active],
    }
    return profile
