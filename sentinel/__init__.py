"""
擎天·规则卫士 — 规则层 Rules
折扣矩阵 + 审核流 + 价格底线 + 风险检查
借鉴 KWeaver BKN Lang：规则用数据定义，不用写死在代码里

V2: 折扣矩阵移至 forge.matrix，引擎逻辑保留在 sentinel.engine
"""

from .engine import (
    check_price_floor,
    get_approver,
    apply_payment_premium,
    apply_warranty_premium,
    DEFAULT_RULES,
    DiscountTier,
    BrandRule,
    ApprovalRule,
    PriceFloor,
)

__all__ = [
    "check_price_floor",
    "get_approver",
    "apply_payment_premium",
    "apply_warranty_premium",
    "DEFAULT_RULES",
    "DiscountTier",
    "BrandRule",
    "ApprovalRule",
    "PriceFloor",
]
