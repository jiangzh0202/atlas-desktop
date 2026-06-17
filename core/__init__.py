"""
擎天·数据底座 — 对象层 + 关系层 + SQLite 持久化
Palantir Ontology 四层映射：Objects / Links / Rules / Actions
"""

import sqlite3, json, os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

DB_DIR = os.environ.get("ATLAS_DATA_DIR", "/srv/atlas/data")
DB_PATH = os.path.join(DB_DIR, "atlas.db")

# ═══════════ 枚举定义 ═══════════

class PricingMode(Enum):
    STANDARD = "standard"
    FIXED_STOCK = "fixed_stock"
    COST_BASED = "cost_based"
    NEGOTIATED = "negotiated"

class QualityGrade(Enum):
    A_PLUS = "A+"; B_PLUS = "B+"; C_PLUS = "C+"; D = "D"

class TradeTerm(Enum):
    FOB = "FOB"; CNF = "CNF"; CIF = "CIF"

class PaymentTerm(Enum):
    PREPAID = "prepaid"; AGAINST_BL = "against_bl"
    NET_15 = "net_15"; NET_30 = "net_30"
    NET_60 = "net_60"; NET_90 = "net_90"

class WarrantyLevel(Enum):
    NONE = "none"; STANDARD = "std"; EXTENDED = "ext"

class Application(Enum):
    TRUCK = "卡车"; MINING = "矿卡"; EXCAVATOR = "挖机"
    CONSTRUCTION = "工程机"; GENERATOR = "发电机组"; BUS = "大巴车"
    SPECIAL = "特种车"; SHIP = "船舶"; POWER_PACK = "动力包"

class ProductLine(Enum):
    FOTON = "福田福康"; DCEC = "东风康明斯"
    CCEC = "康明斯中国"; DFAC = "东风商用车"; SCHAEFFLER = "舍弗勒"

class StarLevel(Enum):
    ONE = 1; TWO = 2; THREE = 3; FOUR = 4; FIVE = 5; SIX = 6; SEVEN = 7

# ═══════════ 对象层 Objects ═══════════

@dataclass
class Part:
    """配件对象"""
    oe_number: str
    alt_oe_list: list = field(default_factory=list)
    name_cn: str = ""; name_ru: str = ""; name_en: str = ""
    brand_channel: str = ""; supply_number: str = ""
    list_price: float = 0.0
    engine_model: str = ""; vehicle_models: list = field(default_factory=list)
    emission_std: str = ""; unit: str = "PC"
    pricing_mode: str = "STANDARD"
    fixed_price: float = 0.0
    cost_with_tax: float = 0.0; cost_without_tax: float = 0.0
    min_order_qty: float = 0.0
    lead_time_days: int = 0
    product_line: str = ""
    applications: list = field(default_factory=list)
    is_active: bool = True
    replacement_oe: str = ""
    competitor_price: float = 0.0

@dataclass
class Customer:
    """客户对象"""
    name_cn: str = ""; name_en: str = ""
    country: str = ""; region: str = ""
    star_level: str = "1"
    annual_purchase: float = 0.0
    preferred_trade: str = "FOB"; preferred_payment: str = "prepaid"
    payment_punctuality: str = ""
    is_blacklisted: bool = False
    tags: list = field(default_factory=list)

@dataclass
class Supplier:
    """供应商对象"""
    name: str
    brands: list = field(default_factory=list)
    contact: str = ""; reliability: str = ""

@dataclass
class QuotationLine:
    """报价行"""
    line_no: int; oe_number: str; part_name_ru: str = ""
    quality: str = "A+"; quantity: int = 1; unit: str = "PC"
    list_price: float = 0.0; discount_pct: float = 0.0
    discount_coeff: float = 1.0
    unit_price: float = 0.0; total_amount: float = 0.0
    pricing_mode: str = "STANDARD"; remark: str = ""

@dataclass
class Quotation:
    """报价单对象"""
    id: str = ""; customer_name: str = ""; date: str = ""
    trade_term: str = "FOB"; payment_term: str = "prepaid"
    lines: list = field(default_factory=list)
    total_amount: float = 0.0
    status: str = "draft"
    created_by: str = ""; reviewed_by: str = ""; approved_by: str = ""

# ═══════════ 关系层 Links ═══════════

# 关系以显式函数表达，每个函数代表一个业务语义
RELATIONS = {
    "part_adapts_engine":     "配件 --适配--> 发动机",
    "engine_mounts_vehicle":   "发动机 --装车--> 车型",
    "part_belongs_brand":      "配件 --属于--> 品牌子渠道",
    "brand_belongs_line":      "品牌 --属于--> 产品线",
    "customer_creates_quote":  "客户 --产生--> 报价单",
    "quote_contains_line":     "报价单 --包含--> 报价行",
    "line_refers_part":        "报价行 --引用--> 配件",
    "supplier_provides_part":  "供应商 --供货--> 配件",
    "part_aliases_oe":         "配件 --别名--> 多个OE号",
}

# ═══════════ 数据库层 ═══════════

def get_db() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            oe_number TEXT UNIQUE NOT NULL,
            alt_oe_numbers TEXT DEFAULT '[]',
            name_cn TEXT, name_ru TEXT, name_en TEXT,
            brand_channel TEXT, supply_number TEXT,
            list_price REAL DEFAULT 0,
            engine_model TEXT, vehicle_models TEXT DEFAULT '[]',
            emission_std TEXT, unit TEXT DEFAULT 'PC',
            pricing_mode TEXT DEFAULT 'STANDARD',
            fixed_price REAL DEFAULT 0,
            cost_with_tax REAL DEFAULT 0,
            cost_without_tax REAL DEFAULT 0,
            min_order_qty REAL DEFAULT 0, lead_time_days INTEGER DEFAULT 0,
            product_line TEXT, applications TEXT DEFAULT '[]',
            is_active INTEGER DEFAULT 1,
            replacement_oe TEXT, competitor_price REAL DEFAULT 0
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS parts_fts USING fts5(
            oe_number, alt_oe_numbers,
            name_cn, name_ru, name_en,
            brand_channel, engine_model, vehicle_models,
            content='parts', content_rowid='id'
        );
        CREATE TABLE IF NOT EXISTS brand_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, product_line TEXT,
            discount_matrix TEXT DEFAULT '{}',
            cap_discount REAL DEFAULT 25.5,
            min_order_amount REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_cn TEXT, name_en TEXT,
            country TEXT, region TEXT,
            star_level TEXT DEFAULT '1',
            annual_purchase REAL DEFAULT 0,
            preferred_trade TEXT DEFAULT 'FOB',
            preferred_payment TEXT DEFAULT 'prepaid',
            payment_punctuality TEXT,
            is_blacklisted INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            brands TEXT DEFAULT '[]', contact TEXT, reliability TEXT
        );
        CREATE TABLE IF NOT EXISTS quotations (
            id TEXT PRIMARY KEY, customer_name TEXT, date TEXT,
            trade_term TEXT DEFAULT 'FOB',
            payment_term TEXT DEFAULT 'prepaid',
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'draft',
            created_by TEXT, reviewed_by TEXT, approved_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS quotation_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id TEXT NOT NULL, line_no INTEGER,
            oe_number TEXT, part_name_ru TEXT,
            quality TEXT DEFAULT 'A+',
            quantity INTEGER DEFAULT 1, unit TEXT DEFAULT 'PC',
            list_price REAL DEFAULT 0,
            discount_pct REAL DEFAULT 0, discount_coeff REAL DEFAULT 1,
            unit_price REAL DEFAULT 0, total_amount REAL DEFAULT 0,
            pricing_mode TEXT DEFAULT 'STANDARD', remark TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id TEXT, step TEXT, detail TEXT,
            oe_number TEXT,
            operator TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

# ═══════════ 查询层（关系查询） ═══════════

def search_parts(query: str, limit: int = 20) -> list:
    """全文搜索：利用别名映射实现语义对齐"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT p.* FROM parts p JOIN parts_fts f ON p.id=f.rowid WHERE parts_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit)
        ).fetchall()
    except:
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM parts WHERE oe_number LIKE ? OR name_cn LIKE ? OR name_ru LIKE ? OR name_en LIKE ? LIMIT ?",
            (like, like, like, like, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_part_by_oe(oe: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM parts WHERE oe_number=?", (oe,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_customer(name: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM customers WHERE name_en LIKE ? OR name_cn LIKE ?", (f"%{name}%", f"%{name}%")).fetchone()
    conn.close()
    return dict(row) if row else None

# ═══════════ 导入 ═══════════

def import_part(part: Part):
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO parts (oe_number, alt_oe_numbers, name_cn, name_ru, name_en,
            brand_channel, supply_number, list_price, engine_model, vehicle_models,
            emission_std, unit, pricing_mode, fixed_price, cost_with_tax,
            cost_without_tax, min_order_qty, lead_time_days, product_line,
            applications, is_active, replacement_oe, competitor_price)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        part.oe_number, json.dumps(part.alt_oe_list),
        part.name_cn, part.name_ru, part.name_en,
        part.brand_channel, part.supply_number, part.list_price,
        part.engine_model, json.dumps(part.vehicle_models),
        part.emission_std, part.unit, part.pricing_mode,
        part.fixed_price, part.cost_with_tax, part.cost_without_tax,
        part.min_order_qty, part.lead_time_days, part.product_line,
        json.dumps(part.applications), int(part.is_active),
        part.replacement_oe, part.competitor_price
    ))
    conn.commit()
    conn.close()

def rebuild_fts():
    conn = get_db()
    conn.execute("INSERT INTO parts_fts(parts_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化: {DB_PATH}")
