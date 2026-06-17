"""
数据底座 — SQLite 数据库 + FTS5 全文索引
"""

import sqlite3
import json
import os
from pathlib import Path

DB_DIR = os.environ.get("ATLAS_DATA_DIR", str(Path(__file__).parent.parent / "data"))
DB_PATH = os.path.join(DB_DIR, "parts.db")
RULES_PATH = os.path.join(DB_DIR, "rules.json")


def get_db() -> sqlite3.Connection:
    """获取数据库连接，自动创建表"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化所有表 + FTS5索引"""
    conn = get_db()
    
    # 配件主表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            oe_number TEXT NOT NULL UNIQUE,
            alt_oe_numbers TEXT DEFAULT '[]',
            name_cn TEXT DEFAULT '',
            name_ru TEXT DEFAULT '',
            name_en TEXT DEFAULT '',
            brand_channel TEXT DEFAULT '',
            supply_number TEXT DEFAULT '',
            list_price REAL DEFAULT 0.0,
            engine_model TEXT DEFAULT '',
            vehicle_model TEXT DEFAULT '',
            emission_std TEXT DEFAULT '',
            unit TEXT DEFAULT 'PC',
            pricing_mode TEXT DEFAULT 'STANDARD',
            fixed_stock_price REAL DEFAULT 0.0,
            cost_with_tax REAL DEFAULT 0.0,
            cost_without_tax REAL DEFAULT 0.0,
            min_order_qty REAL DEFAULT 0.0,
            supplier_name TEXT DEFAULT '',
            lead_time_days INTEGER DEFAULT 0,
            product_line TEXT DEFAULT '',
            application TEXT DEFAULT '[]',
            is_active INTEGER DEFAULT 1,
            replacement_part TEXT DEFAULT '',
            competitor_price REAL DEFAULT 0.0,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # FTS5全文索引（搜OE号+中俄英品名+品牌+适配）
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS parts_fts USING fts5(
            oe_number,
            alt_oe_numbers,
            name_cn,
            name_ru,
            name_en,
            brand_channel,
            engine_model,
            vehicle_model,
            content='parts',
            content_rowid='id'
        )
    """)
    
    # 品牌子渠道表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS brand_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            product_line TEXT DEFAULT '',
            discount_matrix TEXT DEFAULT '{}',
            cap_discount REAL DEFAULT 0.0,
            min_order_amount REAL DEFAULT 0.0,
            supplier_contact TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        )
    """)
    
    # 供应商表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            brands TEXT DEFAULT '[]',
            contact TEXT DEFAULT '',
            payment_terms TEXT DEFAULT '',
            reliability TEXT DEFAULT ''
        )
    """)
    
    # 客户表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_cn TEXT DEFAULT '',
            name_en TEXT DEFAULT '',
            country TEXT DEFAULT '',
            region TEXT DEFAULT '',
            star_level INTEGER DEFAULT 1,
            annual_purchase REAL DEFAULT 0.0,
            preferred_trade TEXT DEFAULT 'FOB',
            preferred_payment TEXT DEFAULT 'prepaid',
            payment_punctuality TEXT DEFAULT '',
            is_blacklisted INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]',
            notes TEXT DEFAULT ''
        )
    """)
    
    # 报价单主表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotations (
            id TEXT PRIMARY KEY,
            customer_name TEXT DEFAULT '',
            customer_contact TEXT DEFAULT '',
            date TEXT DEFAULT '',
            trade_term TEXT DEFAULT 'FOB',
            payment_term TEXT DEFAULT 'prepaid',
            total_amount REAL DEFAULT 0.0,
            status TEXT DEFAULT 'draft',
            created_by TEXT DEFAULT '',
            reviewed_by TEXT DEFAULT '',
            approved_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 报价单行
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotation_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id TEXT NOT NULL,
            line_no INTEGER DEFAULT 0,
            oe_number TEXT DEFAULT '',
            part_name_ru TEXT DEFAULT '',
            quality_grade TEXT DEFAULT 'A+',
            quantity INTEGER DEFAULT 1,
            unit TEXT DEFAULT 'PC',
            unit_price REAL DEFAULT 0.0,
            total_amount REAL DEFAULT 0.0,
            pricing_mode TEXT DEFAULT 'STANDARD',
            list_price REAL DEFAULT 0.0,
            discount_pct REAL DEFAULT 0.0,
            discount_coeff REAL DEFAULT 1.0,
            remark TEXT DEFAULT '',
            FOREIGN KEY (quotation_id) REFERENCES quotations(id)
        )
    """)
    
    # 审计日志
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id TEXT DEFAULT '',
            step TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            oe_number TEXT DEFAULT '',
            values_before TEXT DEFAULT '{}',
            values_after TEXT DEFAULT '{}',
            operator TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_oe ON parts(oe_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_brand ON parts(brand_channel)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_line ON parts(product_line)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quotations_status ON quotations(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_quotation ON audit_log(quotation_id)")
    
    conn.commit()
    conn.close()


def rebuild_fts():
    """重建FTS5全文索引"""
    conn = get_db()
    conn.execute("INSERT INTO parts_fts(parts_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()


def search_parts(query: str, limit: int = 20) -> list:
    """全文搜索配件"""
    conn = get_db()
    try:
        # FTS5搜索，同时匹配OE号+中俄英品名
        rows = conn.execute("""
            SELECT p.* FROM parts p
            JOIN parts_fts fts ON p.id = fts.rowid
            WHERE parts_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # FTS5语法错误时降级为LIKE搜索
        like_q = f"%{query}%"
        rows = conn.execute("""
            SELECT * FROM parts
            WHERE oe_number LIKE ? OR name_cn LIKE ? OR name_ru LIKE ? 
               OR name_en LIKE ? OR engine_model LIKE ? OR vehicle_model LIKE ?
            LIMIT ?
        """, (like_q, like_q, like_q, like_q, like_q, like_q, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化: {DB_PATH}")
    print(f"规则文件路径: {RULES_PATH}")
