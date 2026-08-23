"""作品分级规则表（M5 spec §2 / D24 信号理论）：纯函数查表，LLM 零参与。

短路顺序（spec §2 末尾）：weak 规则（R1/R2）命中即定 → strong 条件（R3/R4）
→ R5-R8 收敛缺省；R7/R8 仅附 reason 不判 grade。
每条 reason 形如 "R{n}: 一句话解释"，命中规则号可解释。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# 精简 CCF-A/B 白名单（~50 条，覆盖 AI/数据/系统/软工/网络/安全 + 综合顶刊）：
# 不是全集，查不到按非顶会处理（宁缺勿滥）；匹配用小写化包含（词边界防误报，
# 如 "update" 不命中 "date"、"washington" 不命中 "ton"）。
CCF_TOP_VENUES: frozenset[str] = frozenset(
    {
        # AI / ML / NLP / CV 会议
        "neurips", "nips", "icml", "iclr", "cvpr", "iccv", "eccv",
        "acl", "emnlp", "naacl", "aaai", "ijcai",
        # 数据挖掘 / 数据库 / Web
        "kdd", "sigir", "www", "icde", "vldb", "sigmod",
        # 系统 / 体系结构 / EDA
        "osdi", "sosp", "nsdi", "micro", "hpca", "isca", "date", "iccad", "dac",
        # 网络
        "infocom", "mobicom", "sigcomm",
        # 安全
        "ccs", "s&p", "usenix security",
        # 软工 / PL
        "pldi", "popl", "fse", "icse", "ase",
        # 实时系统
        "rtas", "rtss",
        # 期刊
        "nature", "science", "pami", "tpami", "ijcv", "jmlr", "tods", "ton", "tifs", "tse",
    }
)

SPAN_STRONG_DAYS = 180  # R3：持续 commit ≥6 个月 ≈ 180 天


def match_ccf_venue(text: str) -> str:
    """小写化包含匹配 CCF 白名单：命中返回表内规范名，未命中返回空串。

    词边界判定（前后不能是字母/数字），避免常见子串误报；sorted 遍历保证确定性。
    """
    lowered = text.strip().lower()
    for name in sorted(CCF_TOP_VENUES):
        if re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", lowered):
            return name
    return ""


def _span_days(facts: dict[str, Any]) -> int:
    """取 repo commit 时间跨度（天）：优先 span_days，缺省从 first/last_commit 推导。"""
    if facts.get("span_days") is not None:
        try:
            return int(facts["span_days"])
        except (TypeError, ValueError):
            return 0
    first, last = str(facts.get("first_commit") or ""), str(facts.get("last_commit") or "")
    if not first or not last:
        return 0
    try:
        d1 = datetime.fromisoformat(first.replace("Z", "+00:00"))
        d2 = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return abs((d2 - d1).days)


def _dominant_language(languages: dict[str, int]) -> tuple[str, float]:
    """语言分布 → (主语言, 占比)；空分布或零字节返回 ("", 0.0)。"""
    if not languages:
        return "", 0.0
    total = sum(languages.values())
    if total <= 0:
        return "", 0.0
    lang = max(languages, key=lambda k: languages[k])
    return lang, languages[lang] / total


def grade_repo(facts: dict[str, Any]) -> tuple[str, list[str]]:
    """仓库分级（R1/R2/R3/R7/R8）：返回 (grade, reasons)，weak 命中即短路。

    R1 is_fork → weak（fork 无原创成本，直接降权）；
    R2 commits<10 → weak（课程作业概率大）；
    R3 持续 commit ≥6 个月 → strong（长期投入难伪造）；
    R7 stars 仅记 reason 不进 grade（可刷，信号弱）；
    R8 主语言占比 >80% 仅记 reason（技术栈一致性佐证）；
    缺省收敛 normal。
    """
    reasons: list[str] = []
    stars = facts.get("stars")
    if stars is not None:
        reasons.append(f"R7: stars={stars}，仅参考不进 grade（可刷）")
    languages = facts.get("languages") or {}
    if isinstance(languages, dict):
        lang, share = _dominant_language({str(k): int(v) for k, v in languages.items()})
        if lang and share > 0.8:
            reasons.append(f"R8: 主语言 {lang} 占比 {share:.0%}>80%，技术栈一致佐证")
    if facts.get("is_fork"):
        reasons.append("R1: fork 无原创成本")
        return "weak", reasons
    commits = facts.get("commits") or 0
    if commits < 10:
        reasons.append(f"R2: commits={commits}<10，课程作业概率大")
        return "weak", reasons
    span = _span_days(facts)
    if span >= SPAN_STRONG_DAYS:
        reasons.append(f"R3: 持续 commit ≥6 个月（span {span} 天），长期投入难伪造")
        return "strong", reasons
    return "normal", reasons


def grade_paper(facts: dict[str, Any]) -> tuple[str, list[str]]:
    """论文分级（R4/R5/R6）：返回 (grade, reasons)。

    first_author 语义为"目标作者名"（查询的作者），一作 ⇔ 其位于 authors[0]；
    R4 一作 + venue ∈ CCF 白名单 → strong；
    R6 非一作 + 顶会 → normal（参与度信号）；
    R5 无 venue（arXiv preprint）→ normal 封顶；一作但非顶会 → normal。
    """
    reasons: list[str] = []
    authors = [str(a) for a in (facts.get("authors") or [])]
    subject = str(facts.get("first_author") or "")
    venue = str(facts.get("venue") or "").strip()
    is_first = bool(authors) and subject == authors[0]
    is_top = bool(venue) and match_ccf_venue(venue) != ""
    if not venue:
        reasons.append("R5: 无 venue（arXiv preprint），normal 封顶")
        return "normal", reasons
    if is_top and is_first:
        reasons.append(f"R4: 一作 + CCF 顶会/顶刊（{venue}），高成本低造假")
        return "strong", reasons
    if is_top:
        reasons.append(f"R6: 非一作 + 顶会（{venue}），参与度信号")
        return "normal", reasons
    if is_first:
        reasons.append(f"R5: 一作但 venue 非 CCF 白名单（{venue}），可信但有更优信号")
    else:
        reasons.append(f"R5: 非顶会 venue 且非一作（{venue}）")
    return "normal", reasons
