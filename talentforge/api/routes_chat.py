"""对话路由：GET/POST /api/chat/turns，意图路由 + 卡片产出。

意图路由（minimal 关键词版，plan 注明后续换 LLM 意图分类）：
1. reply_to 非空（ReflectivePrompt 回答）→ 回答直接沉淀为 trial claim（对话来源）
2. text 含决策关键词（投/看看/岗位/工作/推荐/报告）→ 跑 generate_report 出
   DecisionCard 批 + RiskNote + ReflectivePrompt（jobs 取库，空则给引导文案）
3. 其余 → 自由对话：LLM 生成回复；提及自身情况时经 ProfileUpdatePipeline 补隐式 trial claim

LLM 失败一律降级文案（绝不 500 裸奔）；FakeLLM 注入用于测试。
对话历史为内存态（真模式后续接持久化，见 spec §1）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel

from talentforge.api.common import (
    format_salary,
    load_profile,
    risk_hits,
    save_profile,
    to_claim_card,
)
from talentforge.api.schemas import (
    ChatTurn,
    ClaimCard,
    DecisionCard,
    EvidenceRef,
    JobRef,
    ReflectivePrompt,
    RiskHit,
    RiskNote,
)
from talentforge.domain.profile import ClaimSource, NarrativeClaim, Profile
from talentforge.matcher.coarse import CoarseMatcher
from talentforge.profile.pipeline import ProfileUpdatePipeline
from talentforge.report.generate import generate_report
from talentforge.storage.db import list_jobs

router = APIRouter(tags=["chat"])

DECISION_KEYWORDS = ("投", "看看", "岗位", "工作", "推荐", "报告")
CHAT_KEYWORDS = ("简历", "我", "觉得", "想", "你", "聊聊")
_MENTION_SELF = ("我", "简历", "觉得", "想", "聊聊")

CHAT_SYSTEM_PROMPT = (
    "你是 TalentForge 的求职顾问。你陪伴用户梳理求职决策，语气像书房里的师长："
    "温和、直接、不评判。回应保持简短（2-4 句），基于画像上下文给观点，"
    "不编造用户未说过的事实；不知道就直说。"
)

_WELCOME_TEXT = (
    "我是 TalentForge——你的求职决策伙伴。想聊什么、想问什么、想投什么都可以直接说。"
    "试试：『帮我看看深圳的后端岗位』。"
)


def _now() -> datetime:
    """当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def _intent(text: str, reply_to: str | None) -> str:
    """关键词意图路由：反思回答 > 决策触发 > 自由对话。"""
    if reply_to:
        return "reflective"
    if any(keyword in text for keyword in DECISION_KEYWORDS):
        return "decision"
    return "chat"


def _mentions_self(text: str) -> bool:
    """粗判是否在说自身情况（第一人称/简历/偏好词）。"""
    return any(keyword in text for keyword in _MENTION_SELF)


def _same_claim(a: str, b: str) -> bool:
    """主张文本去重：完全相同或一方包含另一方（短于 4 字不参与包含匹配）。"""
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return a in b or b in a


class TurnPayload(BaseModel):
    """POST /api/chat/turns 请求体：对话文本 + 可选的反思问题回答目标。"""

    text: str
    reply_to: str | None = None


@router.get("/api/chat/turns")
def get_turns(request: Request) -> list[ChatTurn]:
    """返回对话历史（限 50 条）；无持久对话时给 fixture 风格首轮欢迎消息。

    deviation：真模式对话历史为进程内存态，重启即空；持久化后续接入。
    """
    turns: list[ChatTurn] = request.app.state.chat_turns
    if not turns:
        turns.append(ChatTurn(role="assistant", text=_WELCOME_TEXT, cards=[], at=_now()))
    return turns[-50:]


@router.post("/api/chat/turns")
async def post_turn(payload: TurnPayload, request: Request) -> ChatTurn:
    """意图路由处理用户轮次，返回单条 assistant 回复（前端兼容单条/列表）。"""
    state = request.app.state
    text = payload.text.strip()
    user_turn = ChatTurn(role="user", text=text, cards=[], at=_now())
    state.chat_turns.append(user_turn)

    intent = _intent(text, payload.reply_to)
    if intent == "decision":
        assistant = await _decision_reply(request)
    elif intent == "reflective":
        assistant = await _reflective_reply(request, text, payload.reply_to)
    else:
        assistant = await _chat_reply(request, text)
    state.chat_turns.append(assistant)
    return assistant


def _evidence_for(job: Any, item: dict[str, Any]) -> list[EvidenceRef]:
    """从岗位与 report item 组证据链（JD 摘要 + 匹配理由），无证据库时的近似。"""
    evidence: list[EvidenceRef] = []
    snippet = (job.description or "").strip() if job is not None else ""
    if snippet:
        evidence.append(EvidenceRef(kind="jd", ref=str(item.get("url", "")), text=snippet[:200]))
    reason = str(item.get("reason", "")).strip()
    if reason:
        evidence.append(EvidenceRef(kind="system", ref="coarse-match", text=reason[:200]))
    return evidence


async def _decision_reply(request: Request) -> ChatTurn:
    """决策意图：跑 generate_report（复用组件，jobs 从库注入，空库给引导文案）。"""
    state = request.app.state
    conn = state.conn
    jobs = list_jobs(conn, limit=30)
    if not jobs:
        return ChatTurn(
            role="assistant",
            text=(
                "现在还没有可评估的岗位数据——去『工作台』点『生成报告』抓一批岗位"
                "（Boss 抓取需先在『平台源』配置 cookie），"
                "或先跟我聊聊你的求职意向（城市、方向、底线）。"
            ),
            cards=[],
            at=_now(),
        )
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = Profile(name="")
    matcher = CoarseMatcher(state.llm)
    try:
        report = await generate_report(
            profile, "后端", "深圳", limit=len(jobs), matcher=matcher, conn=conn, jobs=jobs
        )
    except Exception as exc:
        return ChatTurn(role="assistant", text=f"生成决策时出了点状况：{exc}", cards=[], at=_now())

    job_by_id = {job.id: job for job in jobs}
    decision_cards: list[DecisionCard] = []
    risk_notes: list[RiskNote] = []
    prompts: list[ReflectivePrompt] = []
    seen_risk: set[str] = set()
    for item in report["items"]:
        job = job_by_id.get(str(item.get("job_id")))
        hits = risk_hits(job) if job is not None else []
        url = str(item.get("url"))
        if url:
            state.decisions[url] = {
                "verdict": str(item.get("verdict")),
                "reason": str(item.get("reason", "")),
            }
        verdict = cast(Literal["apply", "hold", "skip"], str(item.get("verdict")))
        decision_cards.append(
            DecisionCard(
                job=JobRef(
                    title=str(item.get("title")),
                    company=str(item.get("company")),
                    url=url,
                    salary=format_salary(job.salary) if job is not None else "",
                ),
                verdict=verdict,
                reason=str(item.get("reason", "")),
                risk_hits=[
                    RiskHit(key=str(h.get("key", "")), label=str(h.get("label", ""))) for h in hits
                ],
                reflective_question=str(item.get("reflective_question", "")),
                evidence=_evidence_for(job, item),
            )
        )
        for hit in hits:
            key = str(hit.get("key", ""))
            if key and key not in seen_risk:
                seen_risk.add(key)
                risk_notes.append(
                    RiskNote(key=key, label=str(hit.get("label", "")), why=str(hit.get("why", "")))
                )
        question = str(item.get("reflective_question", "")).strip()
        if question:
            prompts.append(ReflectivePrompt(question=question))

    cards: list[Any] = [*decision_cards, *risk_notes, *prompts]
    summary = report.get("summary") or {}
    text = (
        f"给你看了 {len(jobs)} 个岗位：{summary.get('n_apply', 0)} 个可投、"
        f"{summary.get('n_hold', 0)} 个观望、{summary.get('n_skip', 0)} 个排除。"
    )
    return ChatTurn(role="assistant", text=text, cards=cards, at=_now())


def _profile_context(profile: Profile | None) -> str:
    """自由对话的画像上下文摘要（稳定→可变，prompt-cache 合规：变量全在 user）。"""
    if profile is None:
        return "（暂无画像档案）"
    lines = [
        f"姓名：{profile.name or '未知'}",
        f"经验：{profile.years_experience} 年",
        f"技能：{'、'.join(profile.skills) or '未提供'}",
        f"硬边界：{'、'.join(profile.deal_breakers) or '未记录'}",
    ]
    if profile.narrative.identity:
        lines.append(f"一句话叙事：{profile.narrative.identity}")
    return "\n".join(lines)


async def _llm_reply(llm: Any, text: str, profile: Profile | None) -> str:
    """LLM 生成自由对话回复；LLM 不可用/失败时给降级文案，不抛异常。"""
    try:
        user = f"画像上下文：\n{_profile_context(profile)}\n\n用户说：{text}"
        raw = await llm.chat(CHAT_SYSTEM_PROMPT, user)
        return str(raw or "").strip() or "我听着，你继续说。"
    except Exception:
        return "我现在没法连线到推理模型——不过没关系，岗位分析、画像沉淀这些依然可以用。"


async def _add_implicit_claims(request: Request, profile: Profile, text: str) -> list[ClaimCard]:
    """把对话自述当一条 dialogue 事件喂 ProfileUpdatePipeline，LLM 推断并合并 trial claim。

    新增主张写回画像文件并返回 ClaimCard；LLM 失败/无新主张时返回空（不 500）。
    """
    state = request.app.state
    try:
        pipeline = ProfileUpdatePipeline(llm=state.llm)
        event = [
            {
                "event_id": "chat",
                "type": "dialogue",
                "url": "",
                "title": text,
                "source_platform": "chat",
            }
        ]
        updated = await pipeline.ingest_events(profile, event)
        known = {existing.text for existing in profile.narrative_claims}
        new_claims = [c for c in updated.narrative_claims if c.text not in known]
        if new_claims:
            save_profile(updated)
            return [ClaimCard(**to_claim_card(c)) for c in new_claims]
    except Exception:
        return []
    return []


async def _chat_reply(request: Request, text: str) -> ChatTurn:
    """自由对话：LLM 回复 + 提及自身时补隐式 trial claim（画像确认分支）。"""
    state = request.app.state
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = None
    reply = await _llm_reply(state.llm, text, profile)
    cards: list[Any] = []
    if profile is not None and _mentions_self(text):
        cards = await _add_implicit_claims(request, profile, text)
    return ChatTurn(role="assistant", text=reply, cards=cards, at=_now())


async def _reflective_reply(request: Request, text: str, question: str | None) -> ChatTurn:
    """反思回答：把回答沉淀为 trial claim（对话来源 ref=问题），写回画像文件。"""
    cards: list[Any] = []
    text_out = "我记下了你的权衡。"
    try:
        profile = load_profile()
        claim = NarrativeClaim(
            text=text,
            state="trial",
            evidence_count=0,
            confidence=0.5,
            sources=[ClaimSource(kind="dialogue", ref=question or "reflective")],
        )
        if not any(_same_claim(c.text, claim.text) for c in profile.narrative_claims):
            profile.narrative_claims.append(claim)
            save_profile(profile)
            cards.append(ClaimCard(**to_claim_card(claim)))
            text_out = "我把你的权衡记进画像了，之后会留意相关证据。"
    except FileNotFoundError:
        pass
    return ChatTurn(role="assistant", text=text_out, cards=cards, at=_now())
