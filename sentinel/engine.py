"""
擎天·规则引擎 — 规则解释与执行
价格底线检查 + 审核流路由 + 风险溢价
借鉴 KWeaver BKN Lang：规则用数据定义，不用写死在代码里
"""

from dataclasses import dataclass
from typing import Optional


# ═══════════ 规则对象 ═══════════

@dataclass
class DiscountTier:
    """折扣阶梯"""
    price_min: float
    price_max: float
    qty_threshold: Optional[int]     # None=不区分数量
    discount_lt: float               # 数量<阈值时的折扣%
    discount_gte: float              # 数量>=阈值时的折扣%


@dataclass
class BrandRule:
    """品牌折扣规则"""
    brand: str
    tiers: list  # DiscountTier[]
    cap_discount: float = 25.5       # 顶格上限
    min_order_amount: float = 0.0    # 最小订单金额
    special_policy: str = ""         # 特殊政策说明


@dataclass
class ApprovalRule:
    """审核规则"""
    amount_threshold: float
    approver: str


@dataclass
class PriceFloor:
    """价格底线"""
    rule_id: str
    description: str
    check_fn: str  # 检查逻辑描述


# ═══════════ 默认规则配置 ═══════════

DEFAULT_RULES = {
    "approval_flow": [
        {"amount": 50000, "approver": "报价员"},
        {"amount": 200000, "approver": "主管"},
        {"amount": 999999999, "approver": "老板"},
    ],
    "price_floors": [
        {"id": "PF001", "desc": "任何报价不得低于含税进价×1.05"},
        {"id": "PF002", "desc": "ISF3.8缸盖系列最低报价：¥780"},
        {"id": "PF003", "desc": "BOSCH燃油泵：一口价¥2,700"},
    ],
    "payment_risk_premium": {
        "prepaid": 0.0,
        "against_bl": 0.01,
        "net_15": 0.02, "net_30": 0.03,
        "net_60": 0.05, "net_90": 0.08,
    },
    "warranty_premium": {
        "none": 0.0, "std": 0.03, "ext": 0.08,
    },
}


# ═══════════ 规则执行引擎 ═══════════

def check_price_floor(unit_price: float, cost_with_tax: float,
                      part_oe: str = "", rules: dict = None) -> tuple:
    """检查价格底线 → 返回 (是否通过, 原因)

    Args:
        unit_price: 折后单价
        cost_with_tax: 含税进价
        part_oe: 配件 OE 号（用于特殊规则匹配）
        rules: 可选规则 dict

    Returns:
        (passed: bool, reason: str)
    """
    if rules is None:
        rules = DEFAULT_RULES

    # PF001: 不低于含税进价×1.05
    if cost_with_tax > 0 and unit_price < cost_with_tax * 1.05:
        return (False, f"低于底线：{unit_price} < 含税进价{cost_with_tax}×1.05={cost_with_tax * 1.05:.2f}")

    # PF002: ISF3.8缸盖最低780
    if "缸盖" in part_oe or "5258274" in part_oe:
        if unit_price < 780:
            return (False, f"ISF3.8缸盖最低报价¥780，当前{unit_price}")

    return (True, "通过")


def get_approver(total_amount: float, rules: dict = None) -> str:
    """确定审批人

    Args:
        total_amount: 报价总额
        rules: 可选规则 dict

    Returns:
        approver: str — '报价员' / '主管' / '老板'
    """
    if rules is None:
        rules = DEFAULT_RULES
    for step in rules.get("approval_flow", []):
        if total_amount < step["amount"]:
            return step["approver"]
    return "老板"


def apply_payment_premium(base_price: float, payment_term: str,
                          rules: dict = None) -> float:
    """应用付款风险溢价"""
    if rules is None:
        rules = DEFAULT_RULES
    premium = rules.get("payment_risk_premium", {}).get(payment_term, 0.03)
    return base_price * (1 + premium)


def apply_warranty_premium(base_price: float, warranty: str,
                           rules: dict = None) -> float:
    """应用质保溢价"""
    if rules is None:
        rules = DEFAULT_RULES
    premium = rules.get("warranty_premium", {}).get(warranty, 0.03)
    return base_price * (1 + premium)


# ═══════════ 测试 ═══════════

if __name__ == "__main__":
    # 底线检查
    print("底线检查:")
    ok, reason = check_price_floor(1000, 900)
    print(f"  ¥1000 vs 含税进价¥900×1.05=¥945: {'✅' if ok else '❌'} {reason}")
    ok, reason = check_price_floor(700, 900)
    print(f"  ¥700 vs 含税进价¥900×1.05=¥945: {'✅' if ok else '❌'} {reason}")

    # 审核流
    print("\n审核流:")
    for amt in [30000, 150000, 500000]:
        print(f"  总额¥{amt:,.0f} → {get_approver(amt)}审批")
