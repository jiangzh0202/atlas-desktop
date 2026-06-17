"""
擎天·WebSocket 服务 — 端口 3096
将事件总线事件实时推送到所有连接的 WebSocket 客户端

使用线程安全队列桥接 Flask（同步）和 WebSocket（异步）
"""
import asyncio
import json
import queue
import threading

import websockets

# ─── 线程安全事件队列 ───
# Flask 路由通过 publish_ws() 写入，WebSocket 事件循环消费
_event_queue: queue.Queue = queue.Queue()

# ─── 已连接客户端集合 ───
connected_clients: set = set()


def publish_ws(event_type: str, payload: dict = None):
    """
    从任意线程发布事件到 WebSocket 广播队列。
    在 Flask 路由中调用此函数即可将事件推送给所有 WS 客户端。
    
    用法:
        from ws_server import publish_ws
        publish_ws("quotation.completed", {"quote_id": "Q-001"})
    """
    import time
    import uuid
    event = {
        "id": uuid.uuid4().hex[:8],
        "event_type": event_type,
        "payload": payload or {},
        "timestamp": time.time(),
    }
    _event_queue.put(event)


async def _broadcast_loop():
    """消费线程安全队列，广播给所有 WS 客户端"""
    while True:
        try:
            # 非阻塞轮询
            event = _event_queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.1)
            continue

        if not connected_clients:
            continue

        message = json.dumps(event, ensure_ascii=False)
        disconnected = set()
        for ws in list(connected_clients):
            try:
                await ws.send(message)
            except Exception:
                disconnected.add(ws)
        connected_clients.difference_update(disconnected)


async def ws_handler(websocket):
    """处理单个 WebSocket 连接"""
    connected_clients.add(websocket)
    print(f"[ws] 客户端连接 (当前 {len(connected_clients)} 个)")
    try:
        await websocket.send(json.dumps({
            "event_type": "ws.connected",
            "payload": {"message": "已连接 Atlas 事件流"},
            "timestamp": asyncio.get_event_loop().time(),
        }, ensure_ascii=False))
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"[ws] 客户端断开 (当前 {len(connected_clients)} 个)")


async def start_ws_server(host: str = "0.0.0.0", port: int = 3096):
    """启动 WebSocket 服务器（异步）"""
    # 启动广播循环
    asyncio.create_task(_broadcast_loop())

    print(f"🔌 元策·擎天 WebSocket 启动 ws://{host}:{port}")
    async with websockets.serve(ws_handler, host, port):
        await asyncio.Future()  # 永久运行


def run_ws_server(host: str = "0.0.0.0", port: int = 3096):
    """在当前线程运行 WebSocket 服务器（阻塞）"""
    asyncio.run(start_ws_server(host, port))


def start_ws_in_thread(host: str = "0.0.0.0", port: int = 3096):
    """在后台守护线程中启动 WebSocket 服务器"""
    t = threading.Thread(target=run_ws_server, args=(host, port), daemon=True)
    t.start()
    print(f"[ws] WebSocket 服务已在线程中启动")
    return t
