/**
 * 元策·擎天 WebSocket 客户端
 * 连接到 ws://host:3096 接收实时事件推送
 * 
 * 用法：<script src="atlas-ws.js"></script>
 * 然后在页面监听事件：
 *   AtlasWS.on('quotation.completed', (event) => { console.log(event); });
 */
(function () {
  const WS_URL = `ws://${location.hostname}:3096`;
  let ws = null;
  let reconnectTimer = null;
  const listeners = {};

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return;

    console.log('[AtlasWS] 连接中...', WS_URL);
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('[AtlasWS] 已连接 ✅');
      emit('ws.open', {});
    };

    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data);
        const type = event.event_type || 'unknown';
        // 触发对应事件类型的所有监听器
        emit(type, event);
        // 也触发 '*' 通配符监听
        emit('*', event);
      } catch (e) {
        console.warn('[AtlasWS] 消息解析失败', e);
      }
    };

    ws.onclose = () => {
      console.log('[AtlasWS] 已断开');
      emit('ws.close', {});
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.warn('[AtlasWS] 连接错误', err);
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, 3000);
  }

  function emit(type, data) {
    (listeners[type] || []).forEach(fn => {
      try { fn(data); } catch (e) { console.warn('[AtlasWS] 监听器错误', e); }
    });
  }

  // ─── 公开 API ───
  window.AtlasWS = {
    /** 注册事件监听 */
    on(type, fn) {
      if (!listeners[type]) listeners[type] = [];
      listeners[type].push(fn);
    },

    /** 移除监听 */
    off(type, fn) {
      if (!listeners[type]) return;
      listeners[type] = listeners[type].filter(f => f !== fn);
    },

    /** 连接 */
    connect,

    /** 断开 */
    disconnect() {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      if (ws) { ws.close(); ws = null; }
    },

    /** 获取连接状态 */
    get status() {
      return ws ? ws.readyState : WebSocket.CLOSED;
    }
  };

  // ─── 页面加载后自动连接 ───
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }
})();
