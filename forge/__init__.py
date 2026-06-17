"""
擎天·报价工坊 — 行动层 Actions
询盘解析 → 配件匹配 → 规则应用 → 报价计算 → 报价单生成

V2: 拆分为 calculator / matrix / quotation 三个子模块
"""

from .calculator import calculate_line_price
from .matrix import match_discount
from .quotation import generate_quotation, run_quotation, save_quotation

__all__ = [
    "calculate_line_price",
    "match_discount",
    "generate_quotation",
    "run_quotation",
    "save_quotation",
]
