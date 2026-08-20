"""效用轨属性闭集词表（O1/D18 护栏）。

规则：M1 只做精确匹配，认不出落「其他」桶；embedding 近邻归一 M2 挂。
词表替换必须经用户确认（D18）——规范词是用户查询/澄清自己档案的检索锚点。
"""
from __future__ import annotations

VOCAB_VERSION = 1

ATTRIBUTE_VOCAB: tuple[str, ...] = (
    "薪资", "技术栈", "工作模式", "成长空间", "稳定性", "城市",
    "公司类型", "行业", "团队", "加班文化", "福利保障", "氛围",
)
FALLBACK_ATTRIBUTE = "其他"


def resolve_attribute(raw: str) -> str:
    name = str(raw or "").strip()
    return name if name in ATTRIBUTE_VOCAB else FALLBACK_ATTRIBUTE
