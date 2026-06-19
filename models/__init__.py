"""
元策·擎天 用户与公司模型
角色体系：boss(老板) / manager(主管) / quoter(报价员) / purchaser(采购员) / admin(平台管理)

权限矩阵：
  报价API   → quoter / manager / boss
  采购API   → purchaser / manager / boss
  管理API   → manager / boss
  平台API   → admin
  看板      → 所有人（只看自己端的数据）
"""
import sqlite3
import hashlib
import time
import uuid
from pathlib import Path
from config import cfg

DB_PATH = Path(__file__).parent.parent / "data/atlas.db"  # cfg: app.database.path

# ─── 角色定义 ───
ROLES = {
    "boss":       {"label": "老板",    "level": 100, "can": ["quote","procure","manage","platform","dashboard"]},
    "manager":    {"label": "主管",    "level": 80,  "can": ["quote","procure","manage","dashboard"]},
    "quoter":     {"label": "报价员",  "level": 50,  "can": ["quote","dashboard"]},
    "purchaser":  {"label": "采购员",  "level": 50,  "can": ["procure","dashboard"]},
    "admin":      {"label": "平台管理","level": 200, "can": ["platform"]},
}

def role_can(role: str, action: str) -> bool:
    """检查角色是否有某操作权限"""
    return action in ROLES.get(role, {}).get("can", [])

def get_role_label(role: str) -> str:
    return ROLES.get(role, {}).get("label", role)

# ─── 数据库初始化 ───
def init_db():
    """创建用户和公司表（幂等）"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            plan_id TEXT DEFAULT 'starter',
            subscription_end TEXT,
            invite_code TEXT UNIQUE,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT DEFAULT '',
            role TEXT DEFAULT 'quoter',
            company_id TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_orders (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            created_by TEXT,
            supplier TEXT,
            sku_count INTEGER DEFAULT 0,
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'draft',
            approver TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (company_id) REFERENCES companies(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            oe_number TEXT,
            name_cn TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0,
            supplier_name TEXT,
            FOREIGN KEY (order_id) REFERENCES procurement_orders(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT,
            user_id TEXT,
            usage_type TEXT,  -- 'quote' or 'procure'
            units INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    """)

    conn.commit()
    conn.close()

# ─── 初始化管理员 ───
def ensure_admin():
    """首次部署时自动创建管理员账号"""
    init_db()
    admin_cfg = cfg.get("admin", default={})
    email = admin_cfg.get("email", "admin")
    password = admin_cfg.get("password", "admin123")
    name = admin_cfg.get("name", "管理员")
    role = admin_cfg.get("role", "boss")

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # 检查是否已存在
    existing = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if existing:
        conn.close()
        return existing[0]

    # 创建默认公司
    company_id = "COMPANY-DEFAULT"
    c.execute("INSERT OR IGNORE INTO companies (id, name, plan_id) VALUES (?,?,?)",
              (company_id, "默认企业", "starter"))

    # 创建管理员
    uid = f"U-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    pw_hash = hashlib.sha256(f"{email}:{password}:atlas".encode()).hexdigest()
    c.execute("INSERT INTO users (id, email, password_hash, name, role, company_id) VALUES (?,?,?,?,?,?)",
              (uid, email, pw_hash, name, role, company_id))
    conn.commit()
    conn.close()
    print(f"[users] Created admin: {email} role={role} id={uid}")
    return uid

# ─── CRUD ───
def verify_login(email: str, password: str) -> dict | None:
    """验证登录，返回用户 dict 或 None"""
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    pw_hash = hashlib.sha256(f"{email}:{password}:atlas".encode()).hexdigest()
    row = c.execute(
        "SELECT u.*, c.name as company_name, c.plan_id FROM users u LEFT JOIN companies c ON u.company_id=c.id WHERE u.email=? AND u.password_hash=? AND u.status='active'",
        (email, pw_hash)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["role_label"] = get_role_label(d["role"])
        return d
    return None

def get_user(user_id: str) -> dict | None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_users(company_id: str = None) -> list:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if company_id:
        rows = conn.execute("SELECT * FROM users WHERE company_id=? ORDER BY role, name", (company_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM users ORDER BY company_id, role, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_user(email: str, password: str, name: str, role: str, company_id: str) -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    uid = f"U-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    pw_hash = hashlib.sha256(f"{email}:{password}:atlas".encode()).hexdigest()
    c.execute("INSERT INTO users (id, email, password_hash, name, role, company_id) VALUES (?,?,?,?,?,?)",
              (uid, email, pw_hash, name, role, company_id))
    conn.commit()
    conn.close()
    return {"id": uid, "email": email, "name": name, "role": role, "company_id": company_id}

def delete_user(user_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("UPDATE users SET status='deleted' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

def log_usage(company_id: str, user_id: str, usage_type: str, units: int = 1):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO usage_logs (company_id, user_id, usage_type, units) VALUES (?,?,?,?)",
                 (company_id, user_id, usage_type, units))
    conn.commit()
    conn.close()

def get_usage(company_id: str, usage_type: str = None) -> dict:
    """查询公司当月用量"""
    import datetime
    month = datetime.datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    if usage_type:
        row = c.execute(
            "SELECT COALESCE(SUM(units),0) FROM usage_logs WHERE company_id=? AND usage_type=? AND created_at LIKE ?",
            (company_id, usage_type, f"{month}%")
        ).fetchone()
    else:
        row = c.execute(
            "SELECT COALESCE(SUM(units),0) FROM usage_logs WHERE company_id=? AND created_at LIKE ?",
            (company_id, f"{month}%")
        ).fetchone()
    conn.close()
    return {"used": row[0] if row else 0, "month": month}
