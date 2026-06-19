"""
擎天·报价计算器 — 单条配件定价引擎
四种定价模式: STANDARD / FIXED_STOCK / COST_BASED / NEGOTIATED
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .matrix import match_discount
from sentinel import check_price_floor
from config import cfg, get_dimension, get_brand_rules, get_approval_flow


# ═══════════ 12维报价变量 (§8.3) — 全部来自 config ═══════════
# 所有维度系数现在从 config/rules.yaml 的 dimensions 节点读取
# cfg.get('rules','dimensions','<key>') 替代了硬编码 dict


def apply_twelve_dimensions(base_price, dims=None):
    """12维变量叠加"""
    d = dims or {}
    price = base_price
    adj = []

    qg = d.get("quality_grade", "B+")
    qf = cfg.get("rules", "dimensions", "quality_grade", default={}).get(qg, 1.0)
    price *= qf
    adj.append(f"质量档{qg} x{qf}")

    tt = d.get("trade_term", "FOB")
    tf = cfg.get("rules", "dimensions", "trade_term", default={}).get(tt, 1.0)
    price *= tf
    adj.append(f"贸易术语{tt} x{tf}")

    pt = d.get("payment_term", "prepaid")
    pp = cfg.get("rules", "dimensions", "payment_term", default={}).get(pt, 0)
    price *= (1 + pp)
    adj.append(f"付款{pt} +{pp*100:.0f}%")

    reg = d.get("region", "east_asia")
    rf = cfg.get("rules", "dimensions", "region", default={}).get(reg, 1.0)
    price *= rf
    adj.append(f"地区{reg} x{rf}")

    app = d.get("application", "truck")
    af = cfg.get("rules", "dimensions", "application", default={}).get(app, 1.0)
    price *= af
    adj.append(f"场景{app} x{af}")

    war = d.get("warranty", "normal")
    wp = cfg.get("rules", "dimensions", "warranty", default={}).get(war, 0)
    price *= (1 + wp)
    adj.append(f"质保{war} +{wp*100:.0f}%")

    default_margin = cfg.get("rules", "dimensions", "default_profit_margin", default=0.08)
    margin = d.get("profit_margin", default_margin)
    price *= (1 + margin)
    adj.append(f"利润率{margin*100:.0f}%")

    return round(price, 2), adj


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
