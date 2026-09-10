"""事件→画像消费链：事件批经 LLM 推断主张 → trial claims 合并（α 待确认区信号累积）。

与 engine.update_from_feedback 同思路：信号累积不做 LLM 相似度判断，纯文本包含
匹配（相同文本或一方包含另一方），命中即 evidence_count+1 并追加来源。
"""

from __future__ import annotations

from talentforge.domain.profile import ClaimSource, NarrativeClaim, Profile
from talentforge.llm.client import LLMClient
from talentforge.llm.json_utils import extract_json
from talentforge.protocols import ProfileEngine

EVENT_TO_CLAIM_SYSTEM_PROMPT = (
    "你是求职者画像构建器。根据用户消息中的行为事件批（B站/知乎浏览点击记录），"
    "推断其叙事/偏好主张。只输出一个 JSON 对象，不要输出其他文字。格式："
    '{"claims": [{"text": str, "confidence": float, "kind": "narrative"|"preference"}]}。'
    "每条主张必须能从事件内容回溯（可解释来源），不超过 8 条；用中文输出。"
)

_MAX_EVENTS = 50

_MIN_MATCH_LEN = 4


def _same_claim(a: str, b: str) -> bool:
    """主张文本去重：完全相同，或一方包含另一方（短于 min_len 不参与包含匹配）。"""
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < _MIN_MATCH_LEN or len(b) < _MIN_MATCH_LEN:
        return False
    return a in b or b in a


def _event_type(event: dict) -> str:
    """取事件类型：事件直传用 type 字段，DB 读回用 event_type 字段。"""
    value = event.get("type", "")
    if not value:
        value = event.get("event_type", "")
    return str(value)


def _build_user_message(events: list[dict]) -> str:
    """事件批 → user message：每事件一行 `type | url | title | source_platform`。"""
    lines = []
    for event in events:
        parts = [
            _event_type(event),
            str(event.get("url", "")),
            str(event.get("title", "")),
            str(event.get("source_platform", "")),
        ]
        lines.append(" | ".join(parts))
    return "行为事件批（每条一行：type | url | title | source_platform）：\n" + "\n".join(lines)


def _merge_claims(
    existing: list[NarrativeClaim],
    new_claims: list[NarrativeClaim],
    ref: str,
) -> list[NarrativeClaim]:
    """按文本相似合并：命中现有 claim → evidence_count+1 并 append source；未命中新增。"""
    result = [claim.model_copy(deep=True) for claim in existing]
    for claim in new_claims:
        hit = next((item for item in result if _same_claim(item.text, claim.text)), None)
        if hit is not None:
            hit.evidence_count += 1
            hit.sources.append(ClaimSource(kind="behavior", ref=ref))
        else:
            result.append(claim)
    return result


class ProfileUpdatePipeline:
    """事件批 → trial claims 的信号累积管道（α 待确认区）。"""

    def __init__(self, llm: LLMClient, engine: ProfileEngine | None = None) -> None:
        self._llm = llm
        self._engine = engine

    async def ingest_events(self, profile: Profile, events: list[dict]) -> Profile:
        """消费事件批：LLM 推断主张 → 转 trial claims → 与现有 claims 文本去重合并。

        不修改传入 profile（model_copy 深拷贝后操作）。每条新主张的 sources[0] 指向
        批内首个触发事件；与现有主张文本命中时 evidence_count+1 并追加来源。
        """
        updated = profile.model_copy(deep=True)
        if not events:
            return updated
        user_message = _build_user_message(events[:_MAX_EVENTS])
        raw = await self._llm.chat(EVENT_TO_CLAIM_SYSTEM_PROMPT, user_message)
        data = extract_json(raw)
        claims_raw = data.get("claims")
        if not isinstance(claims_raw, list):
            claims_raw = []
        ref = str(events[0].get("event_id", ""))
        new_claims: list[NarrativeClaim] = []
        for item in claims_raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            new_claims.append(
                NarrativeClaim(
                    text=text,
                    confidence=float(item.get("confidence", 0.5)),
                    state="trial",
                    sources=[ClaimSource(kind="behavior", ref=ref)],
                )
            )
        updated.narrative_claims = _merge_claims(updated.narrative_claims, new_claims, ref)
        return updated
