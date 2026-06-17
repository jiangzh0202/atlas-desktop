"""
事件处理器注册 — 所有智能体在此挂载到事件总线
"""
from bus.eventbus import bus, QUOTATION_COMPLETED, STOCK_BELOW_SAFETY, INQUIRY_RECEIVED, PRICE_CHANGED


async def on_price_changed(event: dict):
    """price.changed 事件处理：
    1) 重新检查 sentinel 价格底线
    2) 记录审计日志到 audit_log
    """
    payload = event.get("payload", {})
    oe_number = payload.get("oe_number", "")
    new_price = payload.get("new_price", 0)
    old_price = payload.get("old_price", 0)
    brand = payload.get("brand", "")
    cost_with_tax = payload.get("cost_with_tax", 0.0)
    event_id = event.get("id", "")

    # ── 1) Sentinel 底线重检 ──
    from sentinel.engine import check_price_floor
    passed, reason = check_price_floor(new_price, cost_with_tax, part_oe=oe_number)

    # ── 2) 审计日志 ──
    from ledger.trace import audit
    quote_id = f"PRICE-{event_id}"
    audit.log(
        quotation_id=quote_id,
        step="price.changed",
        agent="sentinel",
        input_data={
            "oe_number": oe_number,
            "old_price": old_price,
            "new_price": new_price,
            "brand": brand,
            "cost_with_tax": cost_with_tax,
        },
        output_data={
            "floor_check_passed": passed,
            "floor_check_reason": reason,
        },
        decision="pass" if passed else "block",
        notes=f"价格从 {old_price} 变更为 {new_price}，底线检查: {reason}"
    )

    # ── 3) 同时写入 SQLite audit_log 表 ──
    try:
        from core import get_db
        db = get_db()
        db.execute(
            "INSERT INTO audit_log (quotation_id, step, detail, oe_number, operator) VALUES (?,?,?,?,?)",
            (quote_id, "price.changed",
             f"价格 {old_price}→{new_price} | 底线检查: {'通过' if passed else '拒绝'} | {reason}",
             oe_number, "sentinel")
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[price.changed] audit_log DB write failed: {e}")

    status = "✅ 通过" if passed else "❌ 拒绝"
    print(f"[price.changed] {oe_number}: {old_price}→{new_price} | 底线: {status} | {reason}")

    return {"ok": True, "floor_passed": passed, "reason": reason}


async def register_all():
    """注册所有智能体的事件处理器"""
    # 仓储智能体: 报价完成 → 减库存
    from agents.warehouse_agent import WarehouseAgent
    warehouse = WarehouseAgent()
    await warehouse.start()

    # 采购智能体: 库存预警 → 补货建议
    from agents.purchasing_agent import PurchasingAgent
    purchasing = PurchasingAgent()
    await purchasing.start()

    # 外贸智能体: 收到询盘 → 翻译
    from agents.trade_agent import TradeAgent
    trade = TradeAgent()
    await trade.start()

    # 价格变更处理器: 重检底线 + 审计日志
    bus.subscribe(PRICE_CHANGED, on_price_changed)

    print("[handlers] 所有智能体已注册到事件总线")
    return {"warehouse": warehouse, "purchasing": purchasing, "trade": trade}
