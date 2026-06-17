"""
别名映射系统 — FTS5 搜索 + AI 建议 + 人工确认

提供：
- search_alias(query)       → FTS5 搜索，返回候选配件列表 (top 5)
- suggest_alias(new_name, oe_number) → 用规则判断是否可能是别名
- add_alias(part_id, alias_text, lang) → 写入别名表
- confirm_alias(alias_id)   → 人工确认别名
- get_aliases(part_id)      → 返回某配件的所有别名
"""

import sqlite3
import json
from difflib import SequenceMatcher
from typing import Optional
from pathlib import Path

from . import get_db, DB_PATH


# ═══════════ 别名表初始化 ═══════════

def init_alias_tables():
    """创建 aliases 表及 FTS5 索引"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL,
            alias_text TEXT NOT NULL,
            lang TEXT DEFAULT 'zh',
            confirmed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (part_id) REFERENCES parts(id)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS aliases_fts USING fts5(
            alias_text,
            lang,
            content='aliases',
            content_rowid='id'
        );
    """)
    conn.commit()
    conn.close()


# ═══════════ 搜索别名 ═══════════

def search_alias(query: str, limit: int = 5) -> list:
    """
    FTS5 全文搜索配件 + 别名，返回候选配件列表。
    搜索范围：parts 表名（name_cn, name_ru, name_en, oe_number）
             + aliases 表的别名文本
    """
    conn = get_db()
    conn.row_factory = sqlite3.Row
    results = []
    seen_ids = set()

    def _try_fts_search(table_fts, sql, params):
        """尝试 FTS5 搜索，失败返回 []"""
        try:
            return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

    # 转义 FTS5 查询：包裹双引号做 phrase 搜索
    fts_query = f'"{query}"'

    # 1) 搜索 parts_fts
    parts_rows = _try_fts_search('parts_fts', """
        SELECT p.id, p.oe_number, p.name_cn, p.name_ru, p.name_en,
               p.brand_channel, p.engine_model, p.list_price,
               1.0 AS confidence, 'part_name' AS match_source
        FROM parts p
        JOIN parts_fts f ON p.id = f.rowid
        WHERE parts_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (fts_query, limit))
    for r in parts_rows:
        d = dict(r)
        if d['id'] not in seen_ids:
            seen_ids.add(d['id'])
            results.append(d)

    # 2) 搜索 aliases_fts
    if len(results) < limit:
        alias_rows = _try_fts_search('aliases_fts', """
            SELECT p.id, p.oe_number, p.name_cn, p.name_ru, p.name_en,
                   p.brand_channel, p.engine_model, p.list_price,
                   0.9 AS confidence, 'alias' AS match_source,
                   a.alias_text AS matched_alias
            FROM aliases a
            JOIN aliases_fts af ON a.id = af.rowid
            JOIN parts p ON a.part_id = p.id
            WHERE aliases_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit - len(results)))
        for r in alias_rows:
            d = dict(r)
            if d['id'] not in seen_ids:
                seen_ids.add(d['id'])
                results.append(d)

    # 3) LIKE fallback: 搜索 parts 表 + aliases 表
    if len(results) < limit:
        like = f"%{query}%"

        # 搜索 parts 名称
        part_like = conn.execute("""
            SELECT id, oe_number, name_cn, name_ru, name_en,
                   brand_channel, engine_model, list_price,
                   0.5 AS confidence, 'like_fallback' AS match_source
            FROM parts
            WHERE oe_number LIKE ? OR name_cn LIKE ? OR name_ru LIKE ? OR name_en LIKE ?
            LIMIT ?
        """, (like, like, like, like, limit - len(results))).fetchall()
        for r in part_like:
            d = dict(r)
            if d['id'] not in seen_ids:
                seen_ids.add(d['id'])
                results.append(d)

        # 搜索 aliases 文本
        if len(results) < limit:
            alias_like = conn.execute("""
                SELECT p.id, p.oe_number, p.name_cn, p.name_ru, p.name_en,
                       p.brand_channel, p.engine_model, p.list_price,
                       0.45 AS confidence, 'alias_like' AS match_source,
                       a.alias_text AS matched_alias
                FROM aliases a
                JOIN parts p ON a.part_id = p.id
                WHERE a.alias_text LIKE ?
                LIMIT ?
            """, (like, limit - len(results))).fetchall()
            for r in alias_like:
                d = dict(r)
                if d['id'] not in seen_ids:
                    seen_ids.add(d['id'])
                    results.append(d)

    conn.close()
    return results[:limit]


# ═══════════ AI 建议别名 ═══════════

def _similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度 (0~1)"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _keyword_overlap(a: str, b: str) -> float:
    """基于关键词重叠的相似度"""
    if not a or not b:
        return 0.0
    # 简单按空格和常见分隔符拆词
    import re
    words_a = set(re.split(r'[\s\-_/()（）]+', a.lower()))
    words_b = set(re.split(r'[\s\-_/()（）]+', b.lower()))
    # 过滤空字符串
    words_a = {w for w in words_a if w}
    words_b = {w for w in words_b if w}
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def suggest_alias(new_name: str, oe_number: str = "", top_n: int = 5) -> list:
    """
    AI 建议：判断 new_name/OE号 是否是已有配件的别名。

    策略：
    1) OE 号精确匹配 → confidence=1.0
    2) OE 号模糊匹配（子串/前缀）→ confidence=0.95
    3) 名称编辑距离 > 0.6 → confidence=0.85
    4) 关键词重叠 > 0.5 → confidence=0.7

    返回候选列表，每项含 part_id, oe_number, name_cn, name_ru, confidence, reason
    """
    conn = get_db()
    conn.row_factory = sqlite3.Row

    candidates = []

    # 获取全部配件（数据量不大时可行；量大时应加索引）
    all_parts = conn.execute(
        "SELECT id, oe_number, name_cn, name_ru, name_en, alt_oe_numbers FROM parts WHERE is_active=1"
    ).fetchall()
    conn.close()

    for part in all_parts:
        part_id = part['id']
        part_oe = part['oe_number']
        name_cn = part['name_cn'] or ''
        name_ru = part['name_ru'] or ''
        name_en = part['name_en'] or ''

        # 解析 alt_oe_numbers JSON
        try:
            alt_oes = json.loads(part['alt_oe_numbers']) if part['alt_oe_numbers'] else []
        except (json.JSONDecodeError, TypeError):
            alt_oes = []

        confidence = 0.0
        reason = ""

        # 策略 1: OE 号精确匹配
        if oe_number and (oe_number.upper() == part_oe.upper() or
                          any(oe_number.upper() == alt.upper() for alt in alt_oes)):
            confidence = 1.0
            reason = f"OE号精确匹配: {oe_number}"
            candidates.append({
                'part_id': part_id, 'oe_number': part_oe,
                'name_cn': name_cn, 'name_ru': name_ru, 'name_en': name_en,
                'confidence': confidence, 'reason': reason
            })
            continue

        # 策略 2: OE 号模糊匹配（包含关系）
        if oe_number and (oe_number.upper() in part_oe.upper() or
                          part_oe.upper() in oe_number.upper()):
            confidence = 0.95
            reason = f"OE号模糊匹配: {oe_number} ↔ {part_oe}"
            candidates.append({
                'part_id': part_id, 'oe_number': part_oe,
                'name_cn': name_cn, 'name_ru': name_ru, 'name_en': name_en,
                'confidence': confidence, 'reason': reason
            })
            continue

        # 策略 3: 名称编辑距离
        if new_name:
            sim_cn = _similarity(new_name, name_cn)
            sim_ru = _similarity(new_name, name_ru)
            sim_en = _similarity(new_name, name_en)
            best_sim = max(sim_cn, sim_ru, sim_en)
            if best_sim >= 0.6:
                lang = 'zh' if best_sim == sim_cn else ('ru' if best_sim == sim_ru else 'en')
                confidence = 0.85 * best_sim  # scale by similarity
                reason = f"名称相似度 {best_sim:.2f} ({lang})"
                candidates.append({
                    'part_id': part_id, 'oe_number': part_oe,
                    'name_cn': name_cn, 'name_ru': name_ru, 'name_en': name_en,
                    'confidence': confidence, 'reason': reason
                })
                continue

        # 策略 4: 关键词重叠
        if new_name:
            ko_cn = _keyword_overlap(new_name, name_cn)
            ko_ru = _keyword_overlap(new_name, name_ru)
            ko_en = _keyword_overlap(new_name, name_en)
            best_ko = max(ko_cn, ko_ru, ko_en)
            if best_ko >= 0.5:
                lang = 'zh' if best_ko == ko_cn else ('ru' if best_ko == ko_ru else 'en')
                confidence = 0.7 * best_ko
                reason = f"关键词重叠 {best_ko:.2f} ({lang})"
                candidates.append({
                    'part_id': part_id, 'oe_number': part_oe,
                    'name_cn': name_cn, 'name_ru': name_ru, 'name_en': name_en,
                    'confidence': confidence, 'reason': reason
                })

    # 按 confidence 降序排列，取 top_n
    candidates.sort(key=lambda x: x['confidence'], reverse=True)
    return candidates[:top_n]


# ═══════════ 别名 CRUD ═══════════

def add_alias(part_id: int, alias_text: str, lang: str = 'zh', confirmed: bool = False) -> dict:
    """
    向别名表写入一条别名记录。
    返回插入的 alias 记录。
    """
    conn = get_db()
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        "INSERT INTO aliases (part_id, alias_text, lang, confirmed) VALUES (?, ?, ?, ?)",
        (part_id, alias_text, lang, int(confirmed))
    )
    alias_id = cursor.lastrowid
    conn.commit()

    row = conn.execute("SELECT * FROM aliases WHERE id = ?", (alias_id,)).fetchone()
    conn.close()
    return dict(row) if row else {'id': alias_id, 'part_id': part_id, 'alias_text': alias_text, 'lang': lang}


def confirm_alias(alias_id: int) -> Optional[dict]:
    """人工确认别名（设置 confirmed=1）"""
    conn = get_db()
    conn.row_factory = sqlite3.Row

    conn.execute("UPDATE aliases SET confirmed = 1 WHERE id = ?", (alias_id,))
    conn.commit()

    row = conn.execute("SELECT * FROM aliases WHERE id = ?", (alias_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_aliases(part_id: int, confirmed_only: bool = False) -> list:
    """返回某配件的所有别名"""
    conn = get_db()
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM aliases WHERE part_id = ?"
    params = [part_id]
    if confirmed_only:
        query += " AND confirmed = 1"

    rows = conn.execute(query + " ORDER BY created_at DESC", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_alias(alias_id: int) -> bool:
    """删除一条别名"""
    conn = get_db()
    conn.execute("DELETE FROM aliases WHERE id = ?", (alias_id,))
    conn.commit()
    conn.close()
    return True


def get_unconfirmed_aliases() -> list:
    """返回所有待确认的 AI 建议别名"""
    conn = get_db()
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT a.*, p.oe_number, p.name_cn, p.name_ru
        FROM aliases a
        JOIN parts p ON a.part_id = p.id
        WHERE a.confirmed = 0
        ORDER BY a.created_at DESC
        LIMIT 100
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════ 一键初始化 ═══════════

def init_all():
    """初始化别名系统所需的所有表"""
    init_alias_tables()
    print("✅ 别名系统表已就绪")


if __name__ == "__main__":
    init_all()

    # 简单冒烟测试
    print("\n--- 搜索测试 ---")
    for r in search_alias("缸盖"):
        print(f"  {r['oe_number']} | {r['name_cn']} | conf={r.get('confidence',0):.2f} | src={r.get('match_source','?')}")

    print("\n--- AI建议测试 ---")
    for r in suggest_alias("ГБЦ", ""):
        print(f"  {r['oe_number']} | {r['name_cn']} | conf={r['confidence']:.2f} | {r['reason']}")
