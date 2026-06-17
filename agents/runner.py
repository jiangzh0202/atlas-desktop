"""
擎天·智能体运行器 — 事件总线启动脚本
启动 EventBus → 注册所有智能体 → 保持运行
"""
import sys
import asyncio
import signal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.eventbus import bus
from agents.warehouse_agent import WarehouseAgent
from agents.purchasing_agent import PurchasingAgent

# 全局智能体实例
warehouse = WarehouseAgent()
purchasing = PurchasingAgent()
all_agents = [warehouse, purchasing]

async def main():
    """启动事件总线和所有智能体"""
    print("=" * 50)
    print("  元策·擎天 Atlas Agent Runner")
    print("=" * 50)

    # 1. 初始化数据库
    try:
        from core import init_db
        init_db()
        print("[Runner] 数据库已就绪")
    except Exception as e:
        print(f"[Runner] 数据库初始化警告: {e}")

    # 2. 启动所有智能体
    for agent in all_agents:
        await agent.start()
    print(f"[Runner] {len(all_agents)} 个智能体已注册")

    # 3. 启动事件总线
    print("[Runner] 事件总线启动，等待事件...")
    print("[Runner] 按 Ctrl+C 停止")

    # 在后台运行总线
    bus_task = asyncio.create_task(bus.start())

    # 等待停止信号
    stop_event = asyncio.Event()

    def _signal_handler():
        print("\n[Runner] 收到停止信号，正在关闭...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            pass

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        print("\n[Runner] 收到中断信号")

    # 4. 清理
    bus.stop()
    bus_task.cancel()
    try:
        await bus_task
    except asyncio.CancelledError:
        pass

    print("[Runner] 所有智能体已停止")

if __name__ == "__main__":
    asyncio.run(main())
