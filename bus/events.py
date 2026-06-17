"""
擎天 Atlas — 事件类型定义
所有智能体间事件类型的常量定义，使用 atlas/agents/base.py 的 AgentEvent dataclass
"""

# 事件类型常量
QUOTATION_COMPLETED = "quotation.completed"
STOCK_BELOW_SAFETY = "stock.below_safety"
PURCHASE_RECEIVED = "purchase.received"
INQUIRY_RECEIVED = "inquiry.received"
PRICE_CHANGED = "price.changed"

# 所有事件类型列表（用于订阅校验/日志）
ALL_EVENT_TYPES = [
    QUOTATION_COMPLETED,
    STOCK_BELOW_SAFETY,
    PURCHASE_RECEIVED,
    INQUIRY_RECEIVED,
    PRICE_CHANGED,
]

# 事件类型 → 中文描述
EVENT_LABELS = {
    QUOTATION_COMPLETED: "报价完成",
    STOCK_BELOW_SAFETY: "库存低于安全线",
    PURCHASE_RECEIVED: "采购到货",
    INQUIRY_RECEIVED: "收到询盘",
    PRICE_CHANGED: "价格变动",
}
