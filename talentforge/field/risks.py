"""场域最小版：结构性风险信号库（政治经济学解释，知情非说教）。

D13/D14 口径：why 讲清"为什么这是剥削/风险"（劳动时间、对价、自由、
法定义务等结构事实），不下道德判词——是可反驳的知情依据，供用户权衡。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from talentforge.domain.job import Job

Severity = Literal["warning", "deal_breaker_candidate"]


@dataclass(frozen=True)
class RiskInfo:
    """结构性风险条目：机器可读 key + 展示 label + 政治经济学解释 why。"""

    key: str
    label: str
    why: str
    severity: Severity


# 库内 8 条覆盖场域常见结构性安排；why 均≥2 句、中性、可反驳。
STRUCTURAL_RISKS: dict[str, RiskInfo] = {
    "996": RiskInfo(
        key="996",
        label="996 工作制",
        why=(
            "996 意味着劳动时间被系统性延长——超时部分通常拿不到加班费，"
            "长期会压缩你恢复和成长的时间（睡眠/学习/社交）。这不是道德判断，"
            "是你需要知情权衡的事实。"
        ),
        severity="deal_breaker_candidate",
    ),
    "大小周": RiskInfo(
        key="大小周",
        label="大小周工作制",
        why=(
            "大小周意味着每隔一周的周六也要上班，法定工时的边界被反复推后。"
            "它多以'行业惯例'出现而未必写入合同，你需要自行确认这种安排"
            "是否伴随相应的加班补偿。"
        ),
        severity="warning",
    ),
    "单休": RiskInfo(
        key="单休",
        label="单休工作制",
        why=(
            "单休意味着每周只休息一天，周间连续劳动后仅有一天恢复窗口。"
            "与双休相比你每年让渡约 48 天休息时间给雇主，"
            "需要判断薪资是否补偿了这部分休息的减少。"
        ),
        severity="warning",
    ),
    "无偿加班": RiskInfo(
        key="无偿加班",
        label="无偿加班",
        why=(
            "无偿加班指超出约定工时的劳动不获得额外报酬，"
            "相当于以零价格购买你的额外劳动时间。劳动法对加班费有明确安排，"
            "这种绕开加班费的约定会系统性压低你的单位时间收入。"
        ),
        severity="deal_breaker_candidate",
    ),
    "竞业限制": RiskInfo(
        key="竞业限制",
        label="竞业限制条款",
        why=(
            "竞业限制会约束你离职后在同业中的就业选择，"
            "本质是限制你今后换雇主的自由。"
            "它可能显著缩小下一份工作的可选范围，"
            "你需要确认条款范围、期限与是否支付竞业补偿金。"
        ),
        severity="deal_breaker_candidate",
    ),
    "加班费模糊": RiskInfo(
        key="加班费模糊",
        label="加班费规则模糊",
        why=(
            "加班费模糊指只提'加班'却不谈计算口径与补偿标准。"
            "模糊本身意味着解释权在你与雇主之间不对等，"
            "入职后很可能按最不利于你的方式执行，值得签约前书面确认。"
        ),
        severity="warning",
    ),
    "无社保": RiskInfo(
        key="无社保",
        label="无社会保险",
        why=(
            "社保是你应得报酬的一部分，覆盖医疗、养老、失业与工伤风险。"
            "无社保意味着这部分应得报酬被雇主截留，"
            "且你持续承担未来福利上的缺口——这是法定义务的缺失，"
            "而非单纯的薪资高低问题。"
        ),
        severity="deal_breaker_candidate",
    ),
    "弹性工作制需核实": RiskInfo(
        key="弹性工作制需核实",
        label="弹性工作制（需核实）",
        why=(
            "弹性工作制在不同公司含义差异很大——有的只是晚到晚走，"
            "有的实质是'任务制'导致工时更长。它本身中性，"
            "但通常缺少工时上限的承诺，需要核实真实考勤规则与加班补偿再判断。"
        ),
        severity="warning",
    ),
}


def assess(job: Job) -> dict[str, object]:
    """评估 Job 的 risk_keys 命中结构性风险，产出 hits 与 field_notes。

    hits 每项为 {key,label,why,severity}；field_notes 把命中条目的 why
    拼成综述；无命中时 hits=[] 且 field_notes=""。未知 risk_key 被忽略。
    """
    hits: list[dict[str, str]] = []
    for key in job.risk_keys:
        info = STRUCTURAL_RISKS.get(key)
        if info is None:
            continue
        hits.append(
            {
                "key": info.key,
                "label": info.label,
                "why": info.why,
                "severity": info.severity,
            }
        )
    field_notes = " ".join(hit["why"] for hit in hits) if hits else ""
    return {"hits": hits, "field_notes": field_notes}
