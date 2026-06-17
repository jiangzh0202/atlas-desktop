#!/bin/bash
# 恩同数据桥 — 快速启动脚本
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

export ATLAS_DATA_DIR="${ATLAS_DATA_DIR:-/srv/atlas/data}"
export BRIDGE_PORT="${BRIDGE_PORT:-3098}"

echo "🔗 启动恩同数据桥 :${BRIDGE_PORT}..."
exec python3 bridge/agent.py
