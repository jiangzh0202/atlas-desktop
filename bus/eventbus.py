"""
擎天·事件总线 — 智能体间的神经
quotation.completed → 仓储减库存 → stock.below_safety → 采购补货
"""
import asyncio
import time
import uuid
from typing import Callable, Awaitable

class EventBus:
    """单例事件总线。V1 用 asyncio.Queue，V2 升级 Redis。"""
    _instance = None

    @classmethod
    def reset(cls):
        """重置单例（测试用）"""
        cls._instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        self._subscribers = {}
        self._queue = asyncio.Queue()
        self._running = False
        self._initialized = True
    
    def subscribe(self, event_type: str, handler: Callable[[dict], Awaitable[None]]):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
    
    async def publish(self, event_type: str, payload: dict = None):
        event = {
            "id": uuid.uuid4().hex[:8],
            "event_type": event_type,
            "payload": payload or {},
            "timestamp": time.time()
        }
        await self._queue.put(event)
    
    async def start(self):
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                handlers = self._subscribers.get(event["event_type"], [])
                for h in handlers:
                    try:
                        await h(event)
                    except Exception as e:
                        print(f"[EventBus] handler error for {event['event_type']}: {e}")
            except asyncio.TimeoutError:
                pass
    
    def stop(self):
        self._running = False

# 全局单例
bus = EventBus()

# ─── 事件类型常量 ───
QUOTATION_COMPLETED = "quotation.completed"
STOCK_BELOW_SAFETY = "stock.below_safety"
PURCHASE_RECEIVED = "purchase.received"
INQUIRY_RECEIVED = "inquiry.received"
PRICE_CHANGED = "price.changed"
