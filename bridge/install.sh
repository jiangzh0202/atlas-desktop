#!/bin/bash
# ═══════════════════════════════════════════════════════════
# 恩同数据桥 — 安装脚本
# 用法: sudo bash bridge/install.sh
#
# 功能:
#   1. 生成 bridge/config.json (默认配置)
#   2. 创建 systemd 服务模板 (enong-bridge.service)
#   3. 安装 Python 依赖
#   4. 创建上传目录 /srv/atlas/data/uploads
# ═══════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BRIDGE_DIR="$SCRIPT_DIR"
DATA_DIR="${ATLAS_DATA_DIR:-/srv/atlas/data}"
BRIDGE_PORT="${BRIDGE_PORT:-3098}"
BRIDGE_USER="${BRIDGE_USER:-www-data}"
BRIDGE_GROUP="${BRIDGE_GROUP:-www-data}"

echo "════════════════════════════════════════"
echo "  恩同数据桥 安装脚本"
echo "════════════════════════════════════════"
echo ""
echo "  项目目录: $PROJECT_DIR"
echo "  数据目录: $DATA_DIR"
echo "  桥接端口: $BRIDGE_PORT"
echo "  运行用户: $BRIDGE_USER:$BRIDGE_GROUP"
echo ""

# ─── 1. 检查 Python3 ───
if ! command -v python3 &>/dev/null; then
    echo "❌ 需要 Python3"
    exit 1
fi
echo "✅ Python3: $(python3 --version)"

# ─── 2. 安装依赖 ───
echo ""
echo "── 安装 Python 依赖 ──"
python3 -m pip install flask flask-cors openpyxl 2>/dev/null || \
    pip3 install flask flask-cors openpyxl || {
    echo "⚠️ pip 安装失败，请手动安装: pip3 install flask flask-cors openpyxl"
}

# ─── 3. 创建目录 ───
echo ""
echo "── 创建目录 ──"
mkdir -p "$DATA_DIR/uploads"
mkdir -p "$DATA_DIR/audit"
chown -R "$BRIDGE_USER:$BRIDGE_GROUP" "$DATA_DIR" 2>/dev/null || true
echo "✅ 数据目录: $DATA_DIR"
echo "✅ 上传目录: $DATA_DIR/uploads"

# ─── 4. 生成默认 config.json ───
echo ""
echo "── 生成配置 ──"
BRIDGE_TOKEN="${BRIDGE_TOKEN:-atlas-bridge-secret-2024}"
CONFIG_FILE="$BRIDGE_DIR/config.json"

cat > "$CONFIG_FILE" << EOFCFG
{
    "bridge_token": "$BRIDGE_TOKEN",
    "data_dir": "$DATA_DIR",
    "port": $BRIDGE_PORT,
    "remote_host": "111.229.196.22",
    "enable_auto_import": false,
    "created_at": "$(date -Iseconds)",
    "security": {
        "mode": "token",
        "tunnel": "placeholder (V3: WireGuard/mTLS)",
        "note": "V2 使用简单 token 认证，V3 升级双向 TLS"
    },
    "watch_dirs": [
        "$DATA_DIR/uploads"
    ],
    "excel_patterns": [
        "*.xlsx",
        "*.xls"
    ],
    "log_level": "INFO"
}
EOFCFG

echo "✅ 配置文件: $CONFIG_FILE"
echo "   Token: $BRIDGE_TOKEN (请在部署后立即修改！)"

# ─── 5. 创建 systemd 服务文件 ───
echo ""
echo "── 创建 systemd 服务 ──"
SERVICE_FILE="/etc/systemd/system/enong-bridge.service"

cat > "/tmp/enong-bridge.service" << EOFSVC
[Unit]
Description=EnTong Data Bridge Agent
After=network.target

[Service]
Type=simple
User=$BRIDGE_USER
Group=$BRIDGE_GROUP
WorkingDirectory=$PROJECT_DIR
Environment="ATLAS_DATA_DIR=$DATA_DIR"
Environment="BRIDGE_PORT=$BRIDGE_PORT"
Environment="BRIDGE_CONFIG=$CONFIG_FILE"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 $PROJECT_DIR/bridge/agent.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=enong-bridge

# 安全加固
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOFSVC

echo "✅ systemd 服务模板已生成: /tmp/enong-bridge.service"
echo ""
echo "  安装到系统:"
echo "    sudo cp /tmp/enong-bridge.service /etc/systemd/system/enong-bridge.service"
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl enable enong-bridge"
echo "    sudo systemctl start enong-bridge"
echo ""

# ─── 6. 生成启动脚本 ───
START_SCRIPT="$BRIDGE_DIR/start.sh"
cat > "$START_SCRIPT" << 'EOFSTART'
#!/bin/bash
# 恩同数据桥 — 快速启动脚本
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

export ATLAS_DATA_DIR="${ATLAS_DATA_DIR:-/srv/atlas/data}"
export BRIDGE_PORT="${BRIDGE_PORT:-3098}"

echo "🔗 启动恩同数据桥 :${BRIDGE_PORT}..."
exec python3 bridge/agent.py
EOFSTART
chmod +x "$START_SCRIPT"
echo "✅ 启动脚本: $START_SCRIPT"

# ─── 7. 健康检查 ───
echo ""
echo "── 启动并验证 ──"
echo "  手动启动测试:"
echo "    cd $PROJECT_DIR && python3 bridge/agent.py &"
echo "    sleep 2"
echo "    curl http://localhost:$BRIDGE_PORT/api/data/ping"
echo ""

# ─── 8. 防火墙提醒 ───
echo "── 防火墙 ──"
echo "  如需外部访问，开放端口:"
echo "    sudo ufw allow $BRIDGE_PORT/tcp"
echo ""
echo "════════════════════════════════════════"
echo "  安装完成！"
echo "════════════════════════════════════════"
