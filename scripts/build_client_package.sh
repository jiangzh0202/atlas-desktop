#!/bin/bash
# ═══════════════════════════════════════════════════════
# 元策·擎天 — 客户站打包脚本（在你的服务器上运行）
# 用法: bash build_client_package.sh --slug enong --name "恩同动力" --domain syenter.com
# 输出: /srv/packages/enong-20260618.zip
# ═══════════════════════════════════════════════════════
set -euo pipefail

SLUG=""; NAME=""; DOMAIN=""; EMAIL="admin@traceclaw.cn"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --slug)   SLUG="$2"; shift 2 ;;
    --name)   NAME="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --email)  EMAIL="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

[[ -z "$SLUG" || -z "$NAME" || -z "$DOMAIN" ]] && {
  echo "用法: $0 --slug <标识> --name <公司名> --domain <域名> [--email <邮箱>]"
  echo "示例: $0 --slug enong --name '恩同动力' --domain syenter.com"
  exit 1
}

ATLAS_API="https://atlas.traceclaw.cn"
PKG_DIR="/srv/packages/${SLUG}"
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/public/images"

echo "📦 打包含户: $NAME ($SLUG) → $DOMAIN"

# ═══════════════════════════════════════════════
# 1. 首页模板（客户可自行替换）
# ═══════════════════════════════════════════════
cat > "$PKG_DIR/public/index.html" << INDEX
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${NAME}</title>
<meta name="description" content="${NAME} — 由元策·擎天 AI 引擎驱动">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f2f2f4;--card:#fff;--green:#7ecf5e;--text:#1a1a2e;--muted:#6e6e73;--radius:12px}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);line-height:1.6}
nav{display:flex;align-items:center;padding:14px 40px;background:rgba(255,255,255,.94);backdrop-filter:blur(12px);position:sticky;top:0;z-index:100;box-shadow:0 1px 3px rgba(0,0,0,.06)}
nav .logo{font-size:1.15rem;font-weight:800;display:flex;align-items:center;gap:6px}
nav .logo span{color:var(--green)}
nav .ai-badge{font-size:.55rem;background:linear-gradient(135deg,#5cb83a,#7ecf5e);color:#fff;padding:2px 8px;border-radius:20px;font-weight:700}
nav .links{margin-left:auto;display:flex;gap:28px;align-items:center}
nav a{text-decoration:none;color:#555;font-size:.85rem;font-weight:500;transition:color .2s}
nav a:hover{color:var(--green)}
nav .btn{background:linear-gradient(135deg,#7ecf5e,#5cb83a);color:#fff!important;padding:10px 24px;border-radius:10px;font-weight:600;transition:all .3s}
nav .btn:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(126,207,94,.3);color:#fff!important}
.hero{text-align:center;padding:100px 40px 50px}
.hero h1{font-size:46px;font-weight:800;margin-bottom:14px;letter-spacing:-.5px}
.hero p{font-size:17px;color:var(--muted);max-width:560px;margin:0 auto 36px;line-height:1.8}
.hero .cta{display:inline-block;background:linear-gradient(135deg,#7ecf5e,#5cb83a);color:#fff;padding:14px 44px;border-radius:14px;font-size:1rem;font-weight:700;text-decoration:none;transition:all .3s}
.hero .cta:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(126,207,94,.35)}
.features{max-width:900px;margin:0 auto 60px;padding:0 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px}
.card{background:var(--card);border-radius:var(--radius);padding:32px 24px;box-shadow:0 1px 4px rgba(0,0,0,.04);text-align:center}
.card .icon{font-size:2.2rem;margin-bottom:12px}
.card h3{font-size:1rem;margin-bottom:8px}
.card p{color:var(--muted);font-size:.85rem;line-height:1.6}
footer{text-align:center;padding:36px;color:#aaa;font-size:.78rem;border-top:1px solid #e5e5ea}
</style>
</head>
<body>
<nav>
  <div class="logo">${NAME} <span class="ai-badge">AI</span></div>
  <div class="links">
    <a href="#">首页</a>
    <a href="#">产品</a>
    <a href="#">关于我们</a>
    <a href="/login" class="btn">管理后台</a>
  </div>
</nav>
<section class="hero">
  <h1>${NAME}</h1>
  <p>由 元策·擎天 AI 引擎驱动<br>智能报价 · 采购管理 · 库存预警 · 一站交付</p>
  <a href="/login" class="cta">进入管理后台 →</a>
</section>
<div class="features">
  <div class="card"><div class="icon">⚡</div><h3>AI 智能报价</h3><p>上传 Excel，3 秒出报价<br>支持 12 维变量精准计算</p></div>
  <div class="card"><div class="icon">📦</div><h3>采购管理</h3><p>多供应商比价<br>订单追踪，库存预警</p></div>
  <div class="card"><div class="icon">🔍</div><h3>图片识别</h3><p>拍照识配件<br>自动匹配 OE 号</p></div>
</div>
<footer>© 2026 ${NAME} | Powered by 元策·擎天 AI</footer>
</body>
</html>
INDEX

echo "   ✅ public/index.html"

# ═══════════════════════════════════════════════
# 2. nginx 配置（所有后端路由 → Atlas）
# ═══════════════════════════════════════════════
cat > "$PKG_DIR/nginx.conf" << NGINX
# ${NAME} — 元策·擎天
# 此文件将被复制到 /etc/nginx/sites-available/${SLUG}

server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};

    root /var/www/${SLUG}/public;
    index index.html;

    # 静态资源缓存
    location /images/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # ═══ 以下全部代理到元策·擎天 Atlas 引擎 ═══
    location /login       { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /admin       { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /dashboard   { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /quotation   { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /procurement { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /parts       { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /history     { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /stock       { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /customers   { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /rules       { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /agents      { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /trade       { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /pricing     { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location /api/        { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; }
    location = /atlas.js  { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; }
    location = /style.css { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; }
    location = /logout    { proxy_pass ${ATLAS_API}; proxy_set_header Host atlas.traceclaw.cn; }

    # SPA fallback — 所有未匹配路由回退到首页
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX

echo "   ✅ nginx.conf"

# ═══════════════════════════════════════════════
# 3. 客户端一键安装脚本
# ═══════════════════════════════════════════════
cat > "$PKG_DIR/install.sh" << 'INSTALLSCRIPT'
#!/bin/bash
# ═══════════════════════════════════════════════════════
# 元策·擎天 — 客户站一键安装
# 在你的 Ubuntu 服务器上运行:
#   sudo bash install.sh
# ═══════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════╗"
echo "║  元策·擎天 网站部署工具                   ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# 检查 root
[[ $EUID -ne 0 ]] && { echo -e "${RED}请用 sudo 运行: sudo bash install.sh${NC}"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SLUG="__SLUG__"
NAME="__NAME__"
DOMAIN="__DOMAIN__"
EMAIL="__EMAIL__"
WWW_DIR="/var/www/${SLUG}/public"

echo "公司: ${NAME}"
echo "域名: ${DOMAIN}"
echo "目录: ${WWW_DIR}"
echo ""

# ═══ 1. 安装依赖 ═══
echo -e "${YELLOW}[1/5] 安装依赖...${NC}"
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx curl

# ═══ 2. 复制网站文件 ═══
echo -e "${YELLOW}[2/5] 部署网站文件...${NC}"
mkdir -p "$WWW_DIR"
cp -r "$SCRIPT_DIR/public/"* "$WWW_DIR/"
chown -R www-data:www-data "/var/www/${SLUG}"

# ═══ 3. 安装 nginx 配置 ═══
echo -e "${YELLOW}[3/5] 配置 nginx...${NC}"
cp "$SCRIPT_DIR/nginx.conf" "/etc/nginx/sites-available/${SLUG}"
ln -sf "/etc/nginx/sites-available/${SLUG}" "/etc/nginx/sites-enabled/${SLUG}"

# 移除默认站点（如果存在）
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
echo -e "${GREEN}   ✅ nginx 配置完成${NC}"

# ═══ 4. 测试 HTTP 可达性 ═══
echo -e "${YELLOW}[4/5] 测试 HTTP...${NC}"
MY_IP=$(curl -s ifconfig.me || echo "未知")
echo "   服务器 IP: ${MY_IP}"

# ═══ 5. 签发 SSL ═══
echo -e "${YELLOW}[5/5] 签发 SSL 证书...${NC}"
echo "   请确保域名 ${DOMAIN} 的 DNS A 记录已指向: ${MY_IP}"
echo "   (TTL 建议 600，等待 DNS 生效后再继续)"
echo ""
read -p "   DNS 已生效？按 Enter 继续签发 SSL (Ctrl+C 跳过)..."

certbot --nginx -d "${DOMAIN}" -d "www.${DOMAIN}" \
  --non-interactive --agree-tos \
  -m "${EMAIL}" --redirect 2>/dev/null && \
  echo -e "${GREEN}   ✅ SSL 已签发${NC}" || \
  echo -e "${YELLOW}   ⚠️ SSL 签发失败，请稍后手动执行:${NC}" && \
  echo "   sudo certbot --nginx -d ${DOMAIN} -d www.${DOMAIN}"

# ═══ 完成 ═══
echo ""
echo -e "${GREEN}┌──────────────────────────────────────────┐"
echo -e "│  🎉 部署完成！                            │"
echo -e "├──────────────────────────────────────────┤"
echo -e "│  官网:  https://${DOMAIN}                   │"
echo -e "│  后台:  https://${DOMAIN}/admin             │"
echo -e "│                                          │"
echo -e "│  ${NAME} 的 Atlas 引擎由 元策·擎天 提供     │"
echo -e "│  订阅管理: https://atlas.traceclaw.cn/pricing │"
echo -e "└──────────────────────────────────────────┘${NC}"
INSTALLSCRIPT

# 替换占位符
sed -i "s/__SLUG__/${SLUG}/g; s/__NAME__/${NAME}/g; s/__DOMAIN__/${DOMAIN}/g; s/__EMAIL__/${EMAIL}/g" "$PKG_DIR/install.sh"
chmod +x "$PKG_DIR/install.sh"

echo "   ✅ install.sh"

# ═══════════════════════════════════════════════
# 4. 打包成 zip
# ═══════════════════════════════════════════════
ZIP_NAME="/srv/packages/${SLUG}-$(date +%Y%m%d).zip"
cd /srv/packages
zip -rq "$ZIP_NAME" "${SLUG}/"
SIZE=$(du -h "$ZIP_NAME" | cut -f1)

echo ""
echo "┌──────────────────────────────────────────┐"
echo "│  📦 打包完成                               │"
echo "├──────────────────────────────────────────┤"
echo "│  文件: ${ZIP_NAME}"
echo "│  大小: ${SIZE}"
echo "│                                          │"
echo "│  发给客户后，客户在服务器上运行:            │"
echo "│  unzip ${SLUG}-*.zip && cd ${SLUG} && sudo bash install.sh │"
echo "└──────────────────────────────────────────┘"
