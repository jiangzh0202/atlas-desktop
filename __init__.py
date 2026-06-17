"""
擎天·规则卫士 — 规则层 Rules
折扣矩阵 + 审核流 + 价格底线 + 风险检查
借鉴 KWeaver BKN Lang：规则用数据定义，不用写死在代码里
"""

import json
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

# ═══════════ 基于真实数据的规则配置 ═══════════

DEFAULT_RULES = {
    "brands": {
        "A2080": {
            "tiers": [
                {"price_min": 0, "price_max": 5, "qty_threshold": None, "discount_lt": 0, "discount_gte": 0},
                {"price_min": 5, "price_max": 50, "qty_threshold": None, "discount_lt": 16, "discount_gte": 16},
                {"price_min": 50, "price_max": 1000, "qty_threshold": 30, "discount_lt": 23, "discount_gte": 24},
                {"price_min": 1000, "price_max": 999999, "qty_threshold": 10, "discount_lt": 24, "discount_gte": 25.5},
            ],
            "cap_discount": 25.5,
            "special_policy": "福田任务未完成 → 可突破顶格多下1-2个点"
        },
        "卡友配": {
            "tiers": [
                {"price_min": 0, "price_max": 100000, "qty_threshold": None, "discount_lt": 15, "discount_gte": 15},
                {"price_min": 100000, "price_max": 999999, "qty_threshold": None, "discount_lt": 18, "discount_gte": 18},
            ],
            "cap_discount": 18,
            "min_order_amount": 30000,
            "special_policy": "供应部王双确认：总额>=10万下18个点"
        },
        "E9300": {
            "tiers": [
                {"price_min": 0, "price_max": 1000, "qty_threshold": None, "discount_lt": 15, "discount_gte": 15},
                {"price_min": 1000, "price_max": 999999, "qty_threshold": 30, "discount_lt": 15, "discount_gte": 17},
            ],
            "cap_discount": 17
        },
        "东亚": {
            "tiers": [
                {"price_min": 0, "price_max": 999999, "qty_threshold": None, "discount_lt": 7, "discount_gte": 7},
            ],
            "cap_discount": 7,
            "special_policy": "国6后处理件：4%"
        },
        "BOSCH": {
            "tiers": [
                {"price_min": 0, "price_max": 999999, "qty_threshold": None, "discount_lt": 24, "discount_gte": 24},
            ],
            "cap_discount": 24
        },
    },
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

def match_discount(brand: str, unit_price: float, quantity: int, rules: dict = None) -> tuple:
    """
    匹配品牌折扣矩阵 → 返回 (折扣%, 折扣系数, 说明)
    规则优先级：品牌精确匹配 > 模糊匹配 > 默认
    """
    if rules is None:
        rules = DEFAULT_RULES

    brand_rules = rules.get("brands", {})
    
    # 精确匹配 + 模糊匹配
    matched_key = None
    if brand in brand_rules:
        matched_key = brand
    else:
        for key in brand_rules:
            if key in brand or brand in key:
                matched_key = key
                break
    
    if matched_key:
        br = brand_rules[matched_key]
        for tier in br["tiers"]:
            if tier["price_min"] <= unit_price <= tier["price_max"]:
                if tier["qty_threshold"] is None:
                    disc = tier["discount_lt"]
                    return (disc, (100 - disc) / 100, f"{brand}:{tier['price_min']}-{tier['price_max']},不限量,{disc}%")
                elif quantity >= tier["qty_threshold"]:
                    disc = tier["discount_gte"]
                    return (disc, (100 - disc) / 100, f"{brand}:{tier['price_min']}-{tier['price_max']},>={tier['qty_threshold']}件,{disc}%")
                else:
                    disc = tier["discount_lt"]
                    return (disc, (100 - disc) / 100, f"{brand}:{tier['price_min']}-{tier['price_max']},<{tier['qty_threshold']}件,{disc}%")
    
    # 模糊匹配
    for key, br in brand_rules.items():
        if key in brand or brand in key:
            disc = br["tiers"][0]["discount_lt"]
            return (disc, (100 - disc) / 100, f"{brand}≈{key},默认{disc}%")
    
    # 默认
    return (15, 0.85, f"{brand}:默认15%")

def check_price_floor(unit_price: float, cost_with_tax: float, part_oe: str = "", rules: dict = None) -> tuple:
    """检查价格底线 → 返回 (是否通过, 原因)"""
    if rules is None:
        rules = DEFAULT_RULES

    # PF001: 不低于含税进价×1.05
    if cost_with_tax > 0 and unit_price < cost_with_tax * 1.05:
        return (False, f"低于底线：{unit_price} < 含税进价{cost_with_tax}×1.05={cost_with_tax*1.05:.2f}")
    
    # PF002: ISF3.8缸盖最低780
    if "缸盖" in part_oe or "5258274" in part_oe:
        if unit_price < 780:
            return (False, f"ISF3.8缸盖最低报价¥780，当前{unit_price}")
    
    return (True, "通过")

def get_approver(total_amount: float, rules: dict = None) -> str:
    """确定审批人"""
    if rules is None:
        rules = DEFAULT_RULES
    for step in rules.get("approval_flow", []):
        if total_amount < step["amount"]:
            return step["approver"]
    return "老板"

def apply_payment_premium(base_price: float, payment_term: str, rules: dict = None) -> float:
    """应用付款风险溢价"""
    if rules is None:
        rules = DEFAULT_RULES
    premium = rules.get("payment_risk_premium", {}).get(payment_term, 0.03)
    return base_price * (1 + premium)

def apply_warranty_premium(base_price: float, warranty: str, rules: dict = None) -> float:
    """应用质保溢价"""
    if rules is None:
        rules = DEFAULT_RULES
    premium = rules.get("warranty_premium", {}).get(warranty, 0.03)
    return base_price * (1 + premium)

# ═══════════ 测试 ═══════════

if __name__ == "__main__":
    # 验证折扣矩阵
    tests = [
        ("A2080", 3, 5, 0, 1.0),
        ("A2080", 30, 5, 16, 0.84),
        ("A2080", 500, 10, 23, 0.77),
        ("A2080", 500, 40, 24, 0.76),
        ("A2080", 5000, 5, 24, 0.76),
        ("A2080", 5000, 20, 25.5, 0.745),
        ("卡友配", 1000, 1, 15, 0.85),
        ("E9300", 2000, 50, 17, 0.83),
        ("东亚", 500, 1, 7, 0.93),
        ("BOSCH", 2000, 1, 24, 0.76),
    ]
    print("折扣矩阵测试:")
    for brand, price, qty, exp_disc, exp_coeff in tests:
        disc, coeff, desc = match_discount(brand, price, qty)
        ok = abs(disc - exp_disc) < 0.1 and abs(coeff - exp_coeff) < 0.01
        print(f"  {'✅' if ok else '❌'} {brand:8} ¥{price:>6} x{qty:>3} → {disc}%/{coeff} (期望{exp_disc}%/{exp_coeff}) {desc}")
    
    # 底线检查
    print("\n底线检查:")
    ok, reason = check_price_floor(1000, 900)
    print(f"  ¥1000 vs 含税进价¥900×1.05=¥945: {'✅' if ok else '❌'} {reason}")
    ok, reason = check_price_floor(700, 900)
    print(f"  ¥700 vs 含税进价¥900×1.05=¥945: {'✅' if ok else '❌'} {reason}")
    
    # 审核流
    print("\n审核流:")
    for amt in [30000, 150000, 500000]:
        print(f"  总额¥{amt:,.0f} → {get_approver(amt)}审批")
