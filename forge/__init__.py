"""
擎天·报价工坊 — 行动层 Actions
询盘解析 → 配件匹配 → 规则应用 → 报价计算 → 报价单生成
"""

import json, uuid, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (Part, Quotation, QuotationLine, get_db, get_part_by_oe, search_parts)
from sentinel import (match_discount, check_price_floor, get_approver)

def calculate_line_price(part: dict, quantity: int, rules: dict = None) -> dict:
    """一条配件 → 一个报价（四种模式）"""
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


def run_quotation(inquiry_lines: list, customer_name: str = "",
                  trade_term: str = "FOB", payment_term: str = "prepaid",
                  warranty: str = "std", rules: dict = None) -> tuple:
    """完整报价流水线"""
    quote = Quotation(
        id=f"Q-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        customer_name=customer_name, date=datetime.now().strftime('%Y-%m-%d'),
        trade_term=trade_term, payment_term=payment_term, status='draft',
    )
    traces = []
    for i, item in enumerate(inquiry_lines):
        oe = item.get('oe', '')
        qty = item.get('qty', 1)
        part = get_part_by_oe(oe)
        if not part:
            candidates = search_parts(oe, limit=3)
            part = candidates[0] if candidates else None
        if not part: continue
        
        result = calculate_line_price(part, qty, rules)
        line = QuotationLine(
            line_no=i+1, oe_number=part['oe_number'],
            part_name_ru=item.get('name_ru', part.get('name_ru', '')),
            quality="A+", quantity=qty, unit=part.get('unit', 'PC'),
            list_price=result.get('list_price', 0),
            discount_pct=result.get('discount_pct', 0),
            discount_coeff=result.get('discount_coeff', 1.0),
            unit_price=result['unit_price'],
            total_amount=result['total_amount'],
            pricing_mode=result['mode'],
        )
        quote.lines.append(line)
        traces.extend(result.get('trace', []))
    
    quote.total_amount = sum(l.total_amount for l in quote.lines)
    quote.status = 'pending_review'
    return quote, traces


def save_quotation(quote: Quotation):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO quotations (id,customer_name,date,trade_term,payment_term,total_amount,status) VALUES(?,?,?,?,?,?,?)",
        (quote.id,quote.customer_name,quote.date,quote.trade_term,quote.payment_term,quote.total_amount,quote.status))
    for line in quote.lines:
        conn.execute("INSERT INTO quotation_lines (quotation_id,line_no,oe_number,part_name_ru,quality,quantity,unit,list_price,discount_pct,discount_coeff,unit_price,total_amount,pricing_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (quote.id,line.line_no,line.oe_number,line.part_name_ru,line.quality,line.quantity,line.unit,line.list_price,line.discount_pct,line.discount_coeff,line.unit_price,line.total_amount,line.pricing_mode))
    conn.commit(); conn.close()
