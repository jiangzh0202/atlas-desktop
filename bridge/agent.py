"""
恩同本地数据桥 Agent — Flask 服务 (端口 3098)

功能:
- /api/data/ping           健康检查
- /api/data/upload         接收 Excel 上传，转存到 /srv/atlas/data/uploads/
- /api/data/status         数据桥状态
- /api/data/config         查看/更新配置
- /api/data/import [POST]  手动触发导入指定 .xlsx 文件
- /api/data/imports [GET]  查看导入历史
- 内置文件监视器：每 10s 轮询 uploads 目录，自动导入新 .xlsx

安全:
- V2: 简单 Token 认证 (占位，V3 升级 mTLS)
- 加密隧道占位 (V3 引入 WireGuard/SSH tunnel)
"""
import sys, os, json, io, hashlib, time, threading
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

# ─── 全局状态 ───
_fs_watcher_running = False
_fs_watcher_thread = None

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


# ═══════════════════════════════════════════════════════════
#  导入历史表初始化
# ═══════════════════════════════════════════════════════════

def _ensure_import_history_table():
    """确保 import_history 表存在"""
    from core import get_db
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS import_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_sha256 TEXT,
            rows_imported INTEGER DEFAULT 0,
            sheets_parsed TEXT,
            status TEXT DEFAULT 'ok',
            error_message TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
#  导入引擎 — 解析 .xlsx 并写入 SQLite
# ═══════════════════════════════════════════════════════════

def _import_xlsx_file(file_path: str) -> dict:
    """
    解析一个 .xlsx 文件并导入 parts 表。
    使用 EnTongWorkbook 解析器提取 Sheet2「报价留底」的配件数据。
    返回: {"ok": True/False, "rows": N, "sheets": [...], "error": "..."}
    """
    from atlas.parsers.enong_workbook import EnTongWorkbook
    from core import get_db, import_part, Part

    result = {
        "ok": False,
        "file": os.path.basename(file_path),
        "rows": 0,
        "sheets": [],
        "error": None
    }

    try:
        wb = EnTongWorkbook(file_path)
        result["sheets"] = wb.wb.sheetnames

        # 解析 Sheet2 报价留底 → 配件记录
        part_records = wb.parse_worksheet()
        if not part_records:
            result["error"] = "报价留底未提取到任何配件记录"
            return result

        # 逐条导入
        imported = 0
        for rec in part_records:
            try:
                part = Part(
                    oe_number=rec.oe_number,
                    name_cn=rec.name_cn,
                    name_ru=rec.name_ru,
                    brand_channel=rec.brand,
                    supply_number=rec.supply_number,
                    list_price=rec.list_price,
                    pricing_mode=rec.pricing_mode,
                    fixed_price=rec.fixed_price,
                    cost_with_tax=rec.cost_with_tax,
                    unit="PC",
                    is_active=True,
                )
                import_part(part)
                imported += 1
            except Exception as e:
                print(f"  ⚠ 导入配件失败 {rec.oe_number}: {e}")

        # 重建全文索引
        from core import rebuild_fts
        rebuild_fts()

        result["ok"] = True
        result["rows"] = imported

    except Exception as e:
        result["error"] = str(e)

    return result


def _record_import_history(file_path: str, result: dict):
    """将导入结果写入 import_history 表"""
    from core import get_db
    try:
        # 计算文件 hash
        sha256 = ""
        try:
            with open(file_path, "rb") as f:
                sha256 = hashlib.sha256(f.read()).hexdigest()
        except Exception:
            pass

        conn = get_db()
        conn.execute(
            """INSERT INTO import_history
               (file_name, file_path, file_sha256, rows_imported, sheets_parsed, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                os.path.basename(file_path),
                str(file_path),
                sha256,
                result.get("rows", 0),
                json.dumps(result.get("sheets", [])),
                "ok" if result.get("ok") else "error",
                result.get("error"),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠ 记录导入历史失败: {e}")


# ═══════════════════════════════════════════════════════════
#  文件监视器 — 每 10s 轮询 uploads 目录
# ═══════════════════════════════════════════════════════════

def _get_imported_files() -> set:
    """从 import_history 获取已导入的文件名集合"""
    from core import get_db
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT file_name FROM import_history WHERE status='ok'"
        ).fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _file_watcher_loop():
    """后台轮询线程：每 10s 扫描 uploads 目录"""
    global _fs_watcher_running
    print("👀 文件监视器已启动 (轮询间隔: 10s)")
    print(f"  监视目录: {UPLOAD_DIR}")

    while _fs_watcher_running:
        try:
            # 每次轮询刷新已导入文件集合（防止手动导入后重复）
            already_imported = _get_imported_files()

            if UPLOAD_DIR.exists():
                xlsx_files = sorted(UPLOAD_DIR.glob("*.xlsx"))
                for fpath in xlsx_files:
                    fname = fpath.name
                    if fname in already_imported:
                        continue

                    print(f"\n📥 检测到新文件: {fname}")
                    print(f"  路径: {fpath}")
                    result = _import_xlsx_file(str(fpath))
                    _record_import_history(str(fpath), result)

                    if result.get("ok"):
                        print(f"  ✅ 导入成功: {result['rows']} 条配件记录")
                    else:
                        print(f"  ❌ 导入失败: {result.get('error')}")

                    already_imported.add(fname)
        except Exception as e:
            print(f"  ⚠ 文件监视器异常: {e}")

        time.sleep(10)

    print("👀 文件监视器已停止")


def start_file_watcher():
    """启动文件监视器后台线程"""
    global _fs_watcher_running, _fs_watcher_thread
    if _fs_watcher_running:
        print("⚠ 文件监视器已在运行")
        return

    _fs_watcher_running = True
    _fs_watcher_thread = threading.Thread(target=_file_watcher_loop, daemon=True)
    _fs_watcher_thread.start()


def stop_file_watcher():
    """停止文件监视器"""
    global _fs_watcher_running
    _fs_watcher_running = False


# ═══════════════════════════════════════════════════════════
#  API 端点
# ═══════════════════════════════════════════════════════════

# ─── 健康检查 ───
@app.route("/api/data/ping")
def ping():
    """健康检查端点"""
    return jsonify({
        "ok": True,
        "service": "enong-data-bridge",
        "version": "2.0.0",
        "port": BRIDGE_PORT,
        "data_dir": str(DATA_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "watcher": {
            "enabled": _fs_watcher_running,
            "interval_sec": 10,
        },
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
        db_stats["imports"] = conn.execute("SELECT COUNT(*) FROM import_history").fetchone()[0]
        conn.close()
    except Exception as e:
        db_stats["error"] = str(e)

    # 最近导入
    recent_imports = []
    try:
        from core import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT file_name, rows_imported, status, imported_at FROM import_history ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()
        for r in rows:
            recent_imports.append({
                "file_name": r[0],
                "rows_imported": r[1],
                "status": r[2],
                "imported_at": r[3],
            })
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "bridge": {
            "port": BRIDGE_PORT,
            "data_dir": str(DATA_DIR),
            "upload_dir": str(UPLOAD_DIR),
            "watcher_running": _fs_watcher_running,
            "recent_uploads": len(upload_info),
            "uploads": upload_info
        },
        "database": db_stats,
        "recent_imports": recent_imports,
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


# ─── 手动导入 ───
@app.route("/api/data/import", methods=["POST"])
@_require_auth
def manual_import():
    """
    手动触发导入指定的 .xlsx 文件。
    请求体 JSON: {"file_name": "20240618_report.xlsx"} 或 {"file_path": "/abs/path/file.xlsx"}
    文件名相对于 UPLOAD_DIR。
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"ok": False, "error": "请求体需为 JSON"}), 400

    file_name = data.get("file_name", "")
    file_path = data.get("file_path", "")

    # 确定文件路径
    if file_path:
        target = Path(file_path)
    elif file_name:
        target = UPLOAD_DIR / file_name
    else:
        return jsonify({"ok": False, "error": "请提供 file_name 或 file_path"}), 400

    if not target.exists():
        return jsonify({"ok": False, "error": f"文件不存在: {target}"}), 404

    if not target.suffix.lower() in ('.xlsx', '.xls'):
        return jsonify({"ok": False, "error": "仅支持 .xlsx / .xls 文件"}), 400

    print(f"\n📥 手动导入触发: {target.name}")
    result = _import_xlsx_file(str(target))
    _record_import_history(str(target), result)

    return jsonify({
        "ok": result["ok"],
        "file": target.name,
        "rows_imported": result["rows"],
        "sheets_parsed": result.get("sheets", []),
        "error": result.get("error"),
    })


# ─── 导入历史 ───
@app.route("/api/data/imports", methods=["GET"])
@_require_auth
def list_imports():
    """
    查询导入历史。
    支持查询参数: ?limit=20 (默认 50)
    """
    limit = request.args.get("limit", 50, type=int)
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    try:
        from core import get_db
        conn = get_db()
        rows = conn.execute(
            "SELECT id, file_name, file_path, file_sha256, rows_imported, sheets_parsed, status, error_message, imported_at FROM import_history ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()

        history = []
        for r in rows:
            history.append({
                "id": r[0],
                "file_name": r[1],
                "file_path": r[2],
                "file_sha256": r[3],
                "rows_imported": r[4],
                "sheets_parsed": json.loads(r[5]) if r[5] else [],
                "status": r[6],
                "error_message": r[7],
                "imported_at": r[8],
            })

        return jsonify({
            "ok": True,
            "count": len(history),
            "imports": history,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
        cfg.setdefault("enable_auto_import", True)
        cfg.setdefault("watcher_interval_sec", 10)
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
            "enable_auto_import": True,
            "watcher_interval_sec": 10,
            "created_at": datetime.now().isoformat()
        }
        CONFIG_PATH.write_text(json.dumps(default_cfg, indent=2, ensure_ascii=False))
        print(f"📝 默认配置已生成: {CONFIG_PATH}")

    # 初始化导入历史表
    _ensure_import_history_table()
    print("📋 导入历史表已就绪")

    # 启动文件监视器
    cfg = {}
    try:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass

    if cfg.get("enable_auto_import", True):
        start_file_watcher()

    print(f"🔗 恩同数据桥启动 :{BRIDGE_PORT}")
    print(f"  数据目录: {DATA_DIR}")
    print(f"  上传目录: {UPLOAD_DIR}")
    print(f"  配置文件: {CONFIG_PATH}")
    print(f"  安全模式: Token 认证 (V2)")
    print(f"  文件监视: {'启用 (10s轮询)' if _fs_watcher_running else '禁用'}")
    print(f"  加密隧道: 占位 (V3 WireGuard/mTLS)")
    app.run(host="0.0.0.0", port=BRIDGE_PORT, debug=False)
