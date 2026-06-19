"""
擎天·折扣矩阵 — 二维矩阵 (品牌 × 单价区间 × 数量阶梯)
借鉴 KWeaver BKN Lang：规则用数据定义，不用写死在代码里
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cfg, get_brand_rules


# ═══════════ 品牌折扣矩阵 — 全部来自 config/rules.yaml ═══════════
# 所有品牌折扣数据现在从 config 的 brands 节点读取
# get_brand_rules() 替代了硬编码的 DEFAULT_BRAND_MATRIX


# ═══════════ 折扣匹配引擎 ═══════════

def match_discount(brand: str, unit_price: float, quantity: int, rules: dict = None) -> tuple:
    """
    匹配品牌折扣矩阵 → 返回 (折扣%, 折扣系数, 说明)
    规则优先级：品牌精确匹配 > 模糊匹配 > 默认

    Args:
        brand: 品牌渠道名
        unit_price: 牌价单价
        quantity: 数量
        rules: 可选，自定义品牌矩阵 dict。若为 dict 且含 "brands" key，则使用 rules["brands"]；
               否则直接作为 brand_rules 使用。None 则使用 config 中的品牌规则。

    Returns:
        (discount_pct: float, coefficient: float, description: str)
    """
    if rules is None:
        brand_rules = get_brand_rules()
    elif isinstance(rules, dict) and "brands" in rules:
        # 兼容 sentinel 的 DEFAULT_RULES 全量格式
        brand_rules = rules.get("brands", {})
    else:
        brand_rules = rules

    # 精确匹配
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
                    return (disc, (100 - disc) / 100,
                            f"{brand}:{tier['price_min']}-{tier['price_max']},不限量,{disc}%")
                elif quantity >= tier["qty_threshold"]:
                    disc = tier["discount_gte"]
                    return (disc, (100 - disc) / 100,
                            f"{brand}:{tier['price_min']}-{tier['price_max']},>={tier['qty_threshold']}件,{disc}%")
                else:
                    disc = tier["discount_lt"]
                    return (disc, (100 - disc) / 100,
                            f"{brand}:{tier['price_min']}-{tier['price_max']},<{tier['qty_threshold']}件,{disc}%")

    # 模糊匹配（遍历所有 key 兜底）
    for key, br in brand_rules.items():
        if key in brand or brand in key:
            disc = br["tiers"][0]["discount_lt"]
            return (disc, (100 - disc) / 100, f"{brand}≈{key},默认{disc}%")

    # 默认
    default_disc = cfg.get("rules", "default_discount_pct", default=15)
    return (default_disc, (100 - default_disc) / 100, f"{brand}:默认{default_disc}%")


# ═══════════ 测试 ═══════════

if __name__ == "__main__":
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
