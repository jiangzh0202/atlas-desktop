"""
擎天·报价计算器 — 单条配件定价引擎
四种定价模式: STANDARD / FIXED_STOCK / COST_BASED / NEGOTIATED
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .matrix import match_discount
from sentinel import check_price_floor


def calculate_line_price(part: dict, quantity: int, rules: dict = None) -> dict:
    """一条配件 → 一个报价（四种模式）

    Args:
        part: 配件 dict，含 oe_number, pricing_mode, list_price, brand_channel,
              fixed_price, cost_with_tax 等字段
        quantity: 数量
        rules: 可选规则 dict（传递给 match_discount 和 check_price_floor）

    Returns:
        dict with unit_price, total_amount, mode, trace, etc.
    """
    trace = []
    oe = part.get('oe_number', '')
    mode = part.get('pricing_mode', 'STANDARD')

    if mode == 'FIXED_STOCK':
        price = part.get('fixed_price', 0) or part.get('list_price', 0)
        trace.append(f"[FIXED_STOCK] 库存一口价: ¥{price}")
        return {'unit_price': price, 'total_amount': price * quantity,
                'mode': 'FIXED_STOCK', 'trace': trace}

    if mode == 'COST_BASED':
        price = part.get('cost_with_tax', 0)
        trace.append(f"[COST_BASED] 含税进价: ¥{price}")
        return {'unit_price': price, 'total_amount': price * quantity,
                'mode': 'COST_BASED', 'trace': trace}

    if mode == 'NEGOTIATED':
        trace.append("[NEGOTIATED] 一单一议")
        return {'unit_price': 0, 'total_amount': 0,
                'mode': 'NEGOTIATED', 'trace': trace}

    # STANDARD: 牌价 × 折扣矩阵
    list_price = part.get('list_price', 0)
    brand = part.get('brand_channel', '')

    disc_pct, coeff, tier_desc = match_discount(brand, list_price, quantity, rules)
    base_price = round(list_price * coeff, 2)

    trace.append(f"[STANDARD] {brand} 牌价¥{list_price}×{quantity} → {tier_desc}")
    trace.append(f"[STANDARD] 折后 ¥{list_price}×{coeff}=¥{base_price}")

    # V1.0: 付款/质保溢价仅做标注，不叠加进单价（真实数据已含在折扣系数里）

    # 底线检查
    cost = part.get('cost_with_tax', 0)
    passed, reason = check_price_floor(base_price, cost, oe, rules)
    trace.append(f"[底线] {'✅' if passed else '❌'} {reason}")

    return {
        'unit_price': base_price, 'total_amount': round(base_price * quantity, 2),
        'mode': 'STANDARD', 'discount_pct': disc_pct, 'discount_coeff': coeff,
        'list_price': list_price, 'trace': trace, 'floor_passed': passed,
    }
