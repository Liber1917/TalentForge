"""主张路由：POST /api/claims/{id}/confirm|reject（α 晋升/归档，D20 用户确认）。

claim 从画像文件读取（TALENTFORGE_PROFILE_PATH 覆盖，缺省 docs/demo/profile.json），
按 claim_id（文本哈希）定位，改状态后写回文件——无持久层时即 profile.json 读写。
confirm：trial→active（evidence_count+1，追加 confirm 来源）；reject：→archived。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from talentforge.api.common import find_claim, load_profile, save_profile, to_claim_card
from talentforge.domain.profile import ClaimSource

router = APIRouter(tags=["claims"])


def _require_profile():
    """加载画像；文件缺失时给出 404（而非 500 裸奔）。"""
    try:
        return load_profile()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/claims/{claim_id}/confirm")
def confirm_claim(claim_id: str) -> dict:
    """主张晋升：trial→active，evidence_count+1 并追加 confirm 来源；非 trial 幂等返回。"""
    profile = _require_profile()
    claim = find_claim(profile, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"主张不存在: {claim_id}")
    if claim.state == "trial":
        claim.state = "active"
        claim.evidence_count += 1
        claim.sources.append(ClaimSource(kind="dialogue", ref=f"confirm:{claim_id}"))
        save_profile(profile)
    return to_claim_card(claim)


@router.post("/api/claims/{claim_id}/reject")
def reject_claim(claim_id: str) -> dict:
    """主张归档：→archived；已归档幂等返回。"""
    profile = _require_profile()
    claim = find_claim(profile, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"主张不存在: {claim_id}")
    if claim.state != "archived":
        claim.state = "archived"
        save_profile(profile)
    return to_claim_card(claim)
