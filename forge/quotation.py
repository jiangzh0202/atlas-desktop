"""
擎天·报价单生成器 — 完整报价单组装与持久化
"""

import uuid
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (Part, Quotation, QuotationLine, get_db, get_part_by_oe, search_parts)
from .calculator import calculate_line_price


def generate_quotation(items: list, customer_name: str = "",
                       trade_term: str = "FOB", payment_term: str = "prepaid",
                       warranty: str = "std", rules: dict = None) -> dict:
    """组装完整报价单

    Args:
        items: 询盘行列表，每行含 oe, qty, name_ru 等
        customer_name: 客户名称
        trade_term: 贸易术语 (FOB/CNF/CIF)
        payment_term: 付款条件 (prepaid/against_bl/net_30...)
        warranty: 质保级别 (none/std/ext)
        rules: 可选规则 dict

    Returns:
        dict with quotation (Quotation object), traces (list), total_amount
    """
    quote = Quotation(
        id=f"Q-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        customer_name=customer_name, date=datetime.now().strftime('%Y-%m-%d'),
        trade_term=trade_term, payment_term=payment_term, status='draft',
    )
    traces = []
    for i, item in enumerate(items):
        oe = item.get('oe', '')
        qty = item.get('qty', 1)
        part = get_part_by_oe(oe)
        if not part:
            candidates = search_parts(oe, limit=3)
            part = candidates[0] if candidates else None
        if not part:
            continue

        result = calculate_line_price(part, qty, rules)
        line = QuotationLine(
            line_no=i + 1, oe_number=part['oe_number'],
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
    return {'quotation': quote, 'traces': traces, 'total_amount': quote.total_amount}


# 向后兼容别名
def run_quotation(inquiry_lines: list, customer_name: str = "",
                  trade_term: str = "FOB", payment_term: str = "prepaid",
                  warranty: str = "std", rules: dict = None) -> tuple:
    """完整报价流水线（向后兼容别名）

    Returns:
        (quotation: Quotation, traces: list)
    """
    result = generate_quotation(inquiry_lines, customer_name,
                                trade_term, payment_term, warranty, rules)
    return result['quotation'], result['traces']


def save_quotation(quote: Quotation):
    """持久化报价单到 SQLite"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO quotations (id,customer_name,date,trade_term,payment_term,total_amount,status) VALUES(?,?,?,?,?,?,?)",
        (quote.id, quote.customer_name, quote.date, quote.trade_term, quote.payment_term, quote.total_amount, quote.status))
    for line in quote.lines:
        conn.execute(
            "INSERT INTO quotation_lines (quotation_id,line_no,oe_number,part_name_ru,quality,quantity,unit,list_price,discount_pct,discount_coeff,unit_price,total_amount,pricing_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (quote.id, line.line_no, line.oe_number, line.part_name_ru, line.quality, line.quantity, line.unit,
             line.list_price, line.discount_pct, line.discount_coeff, line.unit_price, line.total_amount, line.pricing_mode))
    conn.commit()
    conn.close()
