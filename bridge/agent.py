"""
恩同本地数据桥 Agent — Flask 服务 (端口 3098)

功能:
- /api/data/ping           健康检查
- /api/data/upload         接收 Excel 上传，转存到 /srv/atlas/data/uploads/
- /api/data/status         数据桥状态
- /api/data/config         查看/更新配置

安全:
- V2: 简单 Token 认证 (占位，V3 升级 mTLS)
- 加密隧道占位 (V3 引入 WireGuard/SSH tunnel)
"""
import sys, os, json, io, hashlib, time
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

# ─── 路径 ───
sys.path.insert(0, str(Path(__file__).parent.parent))
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", 3098))
DATA_DIR = Path(os.environ.get("ATLAS_DATA_DIR", "/srv/atlas/data"))
UPLOAD_DIR = DATA_DIR / "uploads"
CONFIG_PATH = Path(os.environ.get("BRIDGE_CONFIG", str(Path(__file__).parent / "config.json")))

app = Flask(__name__)
CORS(app)

# ─── Token 认证 (V2 简单版) ───
def _load_token():
    """从配置文件加载认证 token"""
    try:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text())
            return cfg.get("bridge_token", "atlas-bridge-secret-2024")
    except Exception:
        pass
    return os.environ.get("BRIDGE_TOKEN", "atlas-bridge-secret-2024")

def _check_auth():
    """验证请求是否携带有效 token"""
    token = request.headers.get("X-Bridge-Token", "") or request.args.get("token", "")
    expected = _load_token()
    if token != expected:
        return False
    return True

def _require_auth(f):
    """装饰器：需要 token 认证"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _check_auth():
            return jsonify({"ok": False, "error": "未授权：缺少或无效的 bridge token"}), 401
        return f(*args, **kwargs)
    return wrapper


# ─── 健康检查 ───
@app.route("/api/data/ping")
def ping():
    """健康检查端点"""
    return jsonify({
        "ok": True,
        "service": "enong-data-bridge",
        "version": "1.0.0",
        "port": BRIDGE_PORT,
        "data_dir": str(DATA_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "timestamp": time.time(),
        "tunnel": "placeholder (V3: WireGuard/mTLS)"
    })


# ─── 数据桥状态 ───
@app.route("/api/data/status")
def bridge_status():
    """数据桥状态概览"""
    uploads = list(UPLOAD_DIR.glob("*.xlsx")) if UPLOAD_DIR.exists() else []
    upload_info = []
    for f in sorted(uploads, key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
        upload_info.append({
            "name": f.name,
            "size": f.stat().st_size,
            "uploaded_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        })

    # 数据库统计
    db_stats = {}
    try:
        from core import get_db
        conn = get_db()
        db_stats["parts"] = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
        db_stats["stock"] = conn.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
        db_stats["quotations"] = conn.execute("SELECT COUNT(*) FROM quotations").fetchone()[0]
        db_stats["aliases"] = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        conn.close()
    except Exception as e:
        db_stats["error"] = str(e)

    return jsonify({
        "ok": True,
        "bridge": {
            "port": BRIDGE_PORT,
            "data_dir": str(DATA_DIR),
            "upload_dir": str(UPLOAD_DIR),
            "recent_uploads": len(upload_info),
            "uploads": upload_info
        },
        "database": db_stats,
        "security": {
            "auth": "token (V2)",
            "tunnel": "placeholder (V3)",
            "encryption": "none (V3: TLS)"
        }
    })


# ─── Excel 上传 ───
@app.route("/api/data/upload", methods=["POST"])
@_require_auth
def upload_excel():
    """
    接收 Excel 文件上传。
    支持 multipart/form-data，field name = "file"。
    返回文件元数据。
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "缺少 file 字段"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "文件名为空"}), 400

    # 只接受 Excel 文件
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({"ok": False, "error": "仅支持 .xlsx / .xls 文件"}), 400

    # 读取文件内容计算校验和
    content = file.read()
    file.seek(0)
    sha256 = hashlib.sha256(content).hexdigest()
    size = len(content)

    # 创建上传目录
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名: 时间戳_原始文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{file.filename}"
    dest = UPLOAD_DIR / safe_name

    file.save(str(dest))

    return jsonify({
        "ok": True,
        "file": {
            "original_name": file.filename,
            "saved_as": safe_name,
            "path": str(dest),
            "size": size,
            "sha256": sha256,
            "uploaded_at": datetime.now().isoformat()
        }
    })


# ─── 配置管理 ───
@app.route("/api/data/config", methods=["GET", "POST"])
@_require_auth
def manage_config():
    """查看或更新数据桥配置"""
    if request.method == "GET":
        try:
            cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
        except Exception:
            cfg = {}
        cfg.setdefault("bridge_token", "****")
        cfg.setdefault("data_dir", str(DATA_DIR))
        cfg.setdefault("port", BRIDGE_PORT)
        cfg.setdefault("remote_host", "111.229.196.22")
        cfg.setdefault("enable_auto_import", False)
        return jsonify({"ok": True, "config": cfg})

    # POST: 更新配置
    try:
        data = request.get_json(force=True)
        existing = {}
        if CONFIG_PATH.exists():
            existing = json.loads(CONFIG_PATH.read_text())
        existing.update(data)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
        return jsonify({"ok": True, "message": "配置已更新", "config": existing})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ═══════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # 确保默认配置存在
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        default_cfg = {
            "bridge_token": "atlas-bridge-secret-2024",
            "data_dir": str(DATA_DIR),
            "port": BRIDGE_PORT,
            "remote_host": "111.229.196.22",
            "enable_auto_import": False,
            "created_at": datetime.now().isoformat()
        }
        CONFIG_PATH.write_text(json.dumps(default_cfg, indent=2, ensure_ascii=False))
        print(f"📝 默认配置已生成: {CONFIG_PATH}")

    print(f"🔗 恩同数据桥启动 :{BRIDGE_PORT}")
    print(f"  数据目录: {DATA_DIR}")
    print(f"  上传目录: {UPLOAD_DIR}")
    print(f"  配置文件: {CONFIG_PATH}")
    print(f"  安全模式: Token 认证 (V2)")
    print(f"  加密隧道: 占位 (V3 WireGuard/mTLS)")
    app.run(host="0.0.0.0", port=BRIDGE_PORT, debug=False)
