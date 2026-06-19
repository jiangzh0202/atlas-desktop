/**
 * 擎天·擎天 共享模块 V3.1
 * 所有页面引入此文件，自动处理：认证、导航栏、角色隔离、API 调用
 * <script src="/atlas.js"></script>
 */
(function() {
  // ─── 认证 ───
  const TOKEN_KEY = 'atlas_token';
  const EMAIL_KEY = 'atlas_email';

  window.getToken = () => localStorage.getItem(TOKEN_KEY) || '';
  window.saveAuth = (token, email) => {
    localStorage.setItem(TOKEN_KEY, token);
    if (email) localStorage.setItem(EMAIL_KEY, email);
  };
  window.clearAuth = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
  };

  // ─── API 封装（自动带 token）───
  window.api = async (method, path, body) => {
    const opts = {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + getToken()
      }
    };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (r.status === 401) {
      clearAuth();
      window.location.href = '/login';
      throw new Error('unauthorized');
    }
    return r.json();
  };

  // ─── Toast ───
  window.toast = (msg, ok = true) => {
    const t = document.createElement('div');
    t.style.cssText = 'position:fixed;top:16px;right:16px;padding:12px 20px;border-radius:10px;color:#fff;font-size:14px;z-index:9999;animation:slideIn .3s ease;' + (ok ? 'background:#7ecf5e' : 'background:#e74c3c');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2500);
  };

  // ─── 用户信息 ───
  window.userInfo = null;
  window.loadUser = async () => {
    try {
      const d = await api('GET', '/api/me');
      if (d.ok) {
        userInfo = d.data || d.user;
        return userInfo;
      }
    } catch (e) {}
    clearAuth();
    window.location.href = '/login';
    return null;
  };

  // ─── 导航栏注入 ───
  const NAV_HTML = `
<style>
.atlas-nav{display:flex;align-items:center;gap:2px;padding:10px 18px;background:var(--card,#fff);border-bottom:1px solid var(--border,#e8e8e8);position:sticky;top:0;z-index:100;box-shadow:0 1px 8px rgba(0,0,0,.04)}
.atlas-nav .brand{font-weight:700;font-size:16px;color:var(--primary,#7ecf5e);margin-right:10px;text-decoration:none}
.atlas-nav a.nav-item{padding:8px 14px;border-radius:8px;text-decoration:none;font-size:13px;color:var(--text,#333);transition:all .2s;white-space:nowrap}
.atlas-nav a.nav-item:hover,.atlas-nav a.nav-item.active{background:rgba(126,207,94,.12);color:var(--primary,#7ecf5e)}
.atlas-nav .spacer{flex:1}
.atlas-nav .user-badge{font-size:12px;color:var(--text-secondary,#888);margin-right:8px}
.atlas-nav .btn-sm{padding:6px 12px;border-radius:6px;border:1px solid var(--border,#ddd);background:transparent;cursor:pointer;font-size:12px;color:var(--text,#666);transition:all .2s}
.atlas-nav .btn-sm:hover{background:var(--bg,#f5f5f5)}
.hidden{display:none!important}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
</style>
<nav class="atlas-nav" id="atlasNav">
  <a href="/" class="brand">⚙️ 擎天</a>
  <a href="/" class="nav-item" data-page="index">📊 首页</a>
  <a href="/quotation" class="nav-item" data-page="quotation" data-role="quote">💎 报价</a>
  <a href="/parts" class="nav-item" data-page="parts" data-role="quote">🔧 配件</a>
  <a href="/customers" class="nav-item" data-page="customers" data-role="quote">👥 客户</a>
  <a href="/rules" class="nav-item" data-page="rules" data-role="manage">📐 规则</a>
  <a href="/history" class="nav-item" data-page="history" data-role="quote">📜 历史</a>
  <a href="/stock" class="nav-item" data-page="stock" data-role="quote">📦 库存</a>
  <a href="/procurement" class="nav-item" data-page="procurement" data-role="procure">🛒 采购</a>
  <a href="/trade" class="nav-item" data-page="trade" data-role="quote">🌍 外贸</a>
  <a href="/agents" class="nav-item" data-page="agents" data-role="dashboard">🤖 智能体</a>
  <a href="/pricing" class="nav-item" data-page="pricing" data-role="dashboard">💳 套餐</a>
  <a href="/admin" class="nav-item" data-page="admin" data-role="manage">🖥 管理</a>
  <span class="spacer"></span>
  <span class="user-badge" id="userBadge"></span>
  <button class="btn-sm" onclick="clearAuth();location.href='/login'">退出</button>
</nav>
`;

  // ─── 启动：注入导航 + 加载用户 ───
  window.initAtlas = async (currentPage) => {
    // On homepage, don't force redirect — show public content
    if (!getToken()) {
      if (currentPage !== 'index' && currentPage !== '') {
        window.location.href = '/login';
        return null;
      }
      // On index: inject nav with login button instead
      if (!document.getElementById('atlasNav')) {
        const body = document.body;
        body.insertAdjacentHTML('afterbegin', NAV_HTML.replace(
          '<span class="user-badge" id="userBadge"></span>\n  <button class="btn-sm" onclick="clearAuth();location.href=\'/login\'">退出</button>',
          '<a href="/login" class="btn-sm" style="text-decoration:none">登录</a>'
        ));
      }
      return null;
    }

    // 注入导航（如果页面没有自带导航）
    if (!document.getElementById('atlasNav')) {
      const body = document.body;
      body.insertAdjacentHTML('afterbegin', NAV_HTML);
    }

    const user = await loadUser();
    if (!user) return null;

    // 按角色显示/隐藏导航项（当前所有登录用户可看全部）
    const role = user.role || 'quoter';
    document.querySelectorAll('.nav-item[data-role]').forEach(el => {
      const req = el.dataset.role;
      // 所有已登录用户允许查看全部页面
      const roleMap = {
        quote: ['quoter','manager','boss','viewer'],
        procure: ['purchaser','manager','boss','viewer','quoter'],
        manage: ['manager','boss','viewer','quoter'],
        platform: ['admin','viewer','quoter'],
        dashboard: ['quoter','purchaser','manager','boss','admin','viewer'],
      };
      const allowed = roleMap[req] || ['quoter','viewer'];
      el.classList.toggle('hidden', !allowed.includes(role));
    });

    // 高亮当前页
    if (currentPage) {
      document.querySelectorAll('.nav-item[data-page]').forEach(el => {
        el.classList.toggle('active', el.dataset.page === currentPage);
      });
    }

    // 显示用户
    const badge = document.getElementById('userBadge');
    if (badge) badge.textContent = (user.name || user.email) + ' [' + (user.role_label || user.role) + ']';

    return user;
  };
})();
