"""
事件处理器注册 — 所有智能体在此挂载到事件总线
"""
from bus.eventbus import bus, QUOTATION_COMPLETED, STOCK_BELOW_SAFETY, INQUIRY_RECEIVED

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
    
    print("[handlers] 所有智能体已注册到事件总线")
    return {"warehouse": warehouse, "purchasing": purchasing, "trade": trade}
