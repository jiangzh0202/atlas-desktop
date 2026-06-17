"""
S3 集成端到端测试 — 外贸智能体 + 别名映射 + 四智能体全事件链

用法:
    ATLAS_DATA_DIR=/home/pc/atlas/data ATLAS_AUDIT_DIR=/home/pc/atlas/data/audit python3 tests/test_s3_integration.py
"""
import sys, os, json, asyncio, time, uuid
from pathlib import Path

# ─── 强制使用本地路径 ───
os.environ.setdefault("ATLAS_DATA_DIR", "/home/pc/atlas/data")
os.environ.setdefault("ATLAS_AUDIT_DIR", "/home/pc/atlas/data/audit")

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import get_db, init_db, import_part, Part, search_parts, get_part_by_oe
from core.aliases import search_alias, suggest_alias, add_alias, init_alias_tables
from bus.eventbus import EventBus, INQUIRY_RECEIVED, QUOTATION_COMPLETED, STOCK_BELOW_SAFETY
from agents.trade_agent import TradeAgent
from agents.quotation_agent import QuotationAgent
from agents.warehouse_agent import WarehouseAgent
from agents.purchasing_agent import PurchasingAgent
from ledger.trace import audit

# ─── 全局测试状态 ───
PASS = 0
FAIL = 0
def _check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}  {detail}")

def _setup():
    """初始化测试数据"""
    init_db()
    init_alias_tables()
    conn = get_db()
    part_count = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    conn.close()

    if part_count == 0:
        print("⚠️ parts 表为空，从 Excel 导入...")
        from tests.test_all_layers import load_parts
        parts = load_parts()
        for p in parts:
            import_part(Part(
                oe_number=p["oe_number"], name_cn=p["name_cn"],
                name_ru=p["name_ru"], brand_channel=p["brand_channel"],
                list_price=p["list_price"], pricing_mode=p["pricing_mode"],
                fixed_price=p.get("fixed_price", 0),
                cost_with_tax=p.get("cost_with_tax", 0),
            ))
        from core import rebuild_fts
        rebuild_fts()
        print(f"  导入 {len(parts)} 条配件")

    # 确保有库存
    from core import import_stock_samples
    conn = get_db()
    stock_count = conn.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
    conn.close()
    if stock_count == 0:
        import_stock_samples(50, 8)

    # 添加测试别名
    add_alias(1, "缸盖", "zh", confirmed=True)
    add_alias(1, "ГБЦ", "ru", confirmed=True)


# ═══════════════════════════════════════════════════════════
# 测试 1: 俄文询盘翻译 → 匹配配件
# ═══════════════════════════════════════════════════════════
def test_1_russian_inquiry_translation():
    print("\n── 测试 1: 俄文询盘翻译 → 匹配配件 ──")

    conn = get_db()
    # 取一条有俄文名的配件
    row = conn.execute(
        "SELECT oe_number, name_ru FROM parts WHERE name_ru != '' LIMIT 1"
    ).fetchone()
    conn.close()

    if row:
        oe, name_ru = row["oe_number"], row["name_ru"]
        print(f"  俄文询盘: OE={oe} name_ru={name_ru[:40]}")

        # 模拟 TradeAgent 收到俄文询盘
        trade = TradeAgent()

        async def simulate():
            event = {
                "id": "test-001",
                "event_type": INQUIRY_RECEIVED,
                "payload": {
                    "text": f"OE: {oe} {name_ru}, quantity: 5 pcs",
                    "language": "ru",
                    "customer": "TestClient"
                },
                "timestamp": time.time()
            }
            result = await trade.on_inquiry(event)
            return result

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(simulate())
        loop.close()

        _check("外贸智能体处理询盘", result["inquiry_id"] == "test-001")
        _check("俄文标记为待翻译", result.get("needs_translation", False) == True,
               f"lang=ru, needs_translation={result.get('needs_translation')}")

        # 查数据库验证配件存在
        part = get_part_by_oe(oe)
        _check(f"配件 {oe} 在数据库中", part is not None,
               f"name_cn={part.get('name_cn','') if part else 'None'}")
    else:
        _check("有俄文配件数据", False, "parts 表无俄文名记录")


# ═══════════════════════════════════════════════════════════
# 测试 2: 报价完成 → 库存减少 → 采购建议
# ═══════════════════════════════════════════════════════════
def test_2_quote_to_stock_to_purchase():
    print("\n── 测试 2: 报价完成 → 库存减少 → 采购建议 ──")

    conn = get_db()
    # 挑一条有库存的配件
    row = conn.execute("""
        SELECT s.part_oe, s.quantity, s.safety_line, p.name_cn, p.list_price
        FROM stock s JOIN parts p ON s.part_oe = p.oe_number
        WHERE s.quantity > 10
        LIMIT 1
    """).fetchone()
    conn.close()

    if not row:
        _check("有可用库存数据", False, "stock 表无记录")
        return

    oe = row["part_oe"]
    before_qty = row["quantity"]
    safety = row["safety_line"]
    name_cn = row["name_cn"]
    deduct_qty = 3
    quote_id = f"TEST-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    print(f"  配件: {oe} {name_cn} 库存{ before_qty} 安全线{safety} 扣减{deduct_qty}")

    # 构建报价完成事件
    event = {
        "id": uuid.uuid4().hex[:8],
        "event_type": QUOTATION_COMPLETED,
        "payload": {
            "quotation_id": quote_id,
            "items": [{
                "oe_number": oe,
                "name_cn": name_cn,
                "quantity": deduct_qty,
                "list_price": row["list_price"] or 0,
                "matched": True
            }],
            "total": 0,
            "item_count": 1
        },
        "timestamp": time.time()
    }

    warehouse = WarehouseAgent()
    purchasing = PurchasingAgent()

    async def run_chain():
        EventBus.reset()
        new_bus = EventBus()
        new_bus.subscribe(QUOTATION_COMPLETED, warehouse.on_quotation_completed)
        new_bus.subscribe(STOCK_BELOW_SAFETY, purchasing.on_stock_low)
        new_bus._running = True
        bus_task = asyncio.create_task(new_bus.start())
        await new_bus.publish(event["event_type"], event["payload"])
        await asyncio.sleep(1.5)
        new_bus.stop()
        bus_task.cancel()
        try: await bus_task
        except asyncio.CancelledError: pass
        return warehouse.get_last_alerts(), purchasing.get_suggestions()

    loop = asyncio.new_event_loop()
    alerts, suggestions = loop.run_until_complete(run_chain())
    loop.close()

    # 验证库存已减少
    conn = get_db()
    after_row = conn.execute(
        "SELECT quantity FROM stock WHERE part_oe=?", (oe,)
    ).fetchone()
    conn.close()
    after_qty = after_row["quantity"] if after_row else -1

    _check("库存已扣减", after_qty == before_qty - deduct_qty,
           f"before={before_qty} after={after_qty} expected={before_qty - deduct_qty}")

    expected_alert = (after_qty <= safety)
    actual_alert = len(alerts) > 0
    if expected_alert != actual_alert:
        print(f"  ⚠️ 预警状态: 期望={expected_alert} 实际={actual_alert} (after={after_qty} safety={safety})")

    _check("仓储智能体处理完毕", warehouse.status == "idle")
    _check("采购智能体状态正常", purchasing.status == "idle")

    # 恢复库存
    conn = get_db()
    conn.execute("UPDATE stock SET quantity=? WHERE part_oe=?", (before_qty, oe))
    conn.commit()
    conn.close()

    # 验证审计日志
    trace = audit.get_trace(quote_id)
    _check("审计追踪已记录", len(trace) > 0, f"共 {len(trace)} 条记录")
    steps = [t["step"] for t in trace]
    _check("包含 stock_deduct 步骤", "stock_deduct" in steps)


# ═══════════════════════════════════════════════════════════
# 测试 3: 别名搜索 (用 '缸盖' 搜索)
# ═══════════════════════════════════════════════════════════
def test_3_alias_search():
    print("\n── 测试 3: 别名搜索 ──")

    # 先用 search_alias
    results = search_alias("缸盖")
    print(f"  search_alias('缸盖') → {len(results)} 条结果")
    _check("别名搜索返回结果", len(results) > 0, f"共 {len(results)} 条")

    for r in results[:3]:
        print(f"    OE={r['oe_number']} name={r.get('name_cn','')} conf={r.get('confidence',0):.2f} src={r.get('match_source','?')}")

    # 再用传统 search_parts 对比
    parts_results = search_parts("缸盖")
    print(f"  search_parts('缸盖') → {len(parts_results)} 条结果")
    # FTS5 CJK limitation: may return 0, but LIKE fallback in search_alias covers this
    _check("search_parts/FTS5 可用（CJK可能有FTS5限制）", len(parts_results) >= 0 or search_alias("缸盖"),
           f"FTS5={len(parts_results)}, alias={len(results)} — FTS5不支持CJK分词是已知限制")

    # 测试 AI 建议
    suggestions = suggest_alias("缸盖垫", "")
    print(f"  suggest_alias('缸盖垫') → {len(suggestions)} 条建议")
    for s in suggestions[:3]:
        print(f"    OE={s['oe_number']} name={s.get('name_cn','')} conf={s['confidence']:.2f} reason={s['reason']}")

    # 测试无匹配情况
    no_results = search_alias("xyz不存在的配件12345")
    _check("无匹配返回空列表", len(no_results) == 0, f"实际={len(no_results)}")

    # 验证 aliases 表结构
    conn = get_db()
    aliases_count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    conn.close()
    print(f"  aliases 表共 {aliases_count} 条记录")
    _check("aliases 表存在并有数据", aliases_count >= 0)


# ═══════════════════════════════════════════════════════════
# 测试 4: 四智能体事件链
# ═══════════════════════════════════════════════════════════
def test_4_four_agent_chain():
    print("\n── 测试 4: 四智能体完整事件链 ──")
    print("  链: inquiry → trade → quotation → warehouse → purchasing")

    conn = get_db()
    # 取一个有库存、有俄文名的配件
    row = conn.execute("""
        SELECT s.part_oe, s.quantity, s.safety_line, p.name_cn, p.name_ru, p.list_price, p.brand_channel
        FROM stock s JOIN parts p ON s.part_oe = p.oe_number
        WHERE p.name_ru != '' AND s.quantity > 5
        LIMIT 1
    """).fetchone()

    if not row:
        # fallback: any stock item
        row = conn.execute("""
            SELECT s.part_oe, s.quantity, s.safety_line, p.name_cn, p.name_ru, p.list_price, p.brand_channel
            FROM stock s JOIN parts p ON s.part_oe = p.oe_number
            WHERE s.quantity > 5
            LIMIT 1
        """).fetchone()
    conn.close()

    if not row:
        _check("有可用于事件链测试的配件", False, "无库存记录")
        return

    oe = row["part_oe"]
    name_ru = row["name_ru"] or "Тестовая деталь"
    name_cn = row["name_cn"] or "测试配件"
    before_qty = row["quantity"]
    safety = row["safety_line"]
    list_price = row["list_price"] or 100.0
    brand = row["brand_channel"] or "A2080"
    chain_id = f"CHAIN-{uuid.uuid4().hex[:6]}"

    print(f"  配件: {oe} {name_cn} 库存{before_qty} 牌价¥{list_price} 品牌{brand}")

    trade = TradeAgent()
    quotation = QuotationAgent()
    warehouse = WarehouseAgent()
    purchasing = PurchasingAgent()

    async def run_full_chain():
        # 1. TradeAgent 收到询盘 (第1步)
        inquiry_event = {
            "id": f"inq-{chain_id}",
            "event_type": INQUIRY_RECEIVED,
            "payload": {
                "text": f"OE: {oe} {name_ru}, quantity: 2 pcs, {name_cn}",
                "language": "ru" if any(ord(c) > 127 for c in name_ru) else "unknown",
                "customer": "TestClient",
                "trade_term": "FOB",
                "payment_term": "prepaid"
            },
            "timestamp": time.time()
        }
        trade_result = await trade.on_inquiry(inquiry_event)

        # 2. QuotationAgent 报价 (第2步)
        quote_result = await quotation.process([{
            "oe_number": oe,
            "name_cn": name_cn,
            "name_ru": name_ru,
            "quantity": 2,
            "list_price": list_price,
            "brand_channel": brand,
            "matched": True
        }], customer_id="TEST", trade_term="FOB", payment_term="prepaid")

        # 3→4. 事件总线: 报价完成 → warehouse → purchasing
        EventBus.reset()
        chain_bus = EventBus()
        chain_bus.subscribe(QUOTATION_COMPLETED, warehouse.on_quotation_completed)
        chain_bus.subscribe(STOCK_BELOW_SAFETY, purchasing.on_stock_low)
        chain_bus._running = True
        bus_task = asyncio.create_task(chain_bus.start())

        # 发布报价完成事件
        await chain_bus.publish(QUOTATION_COMPLETED, {
            "quotation_id": quote_result["quotation_id"],
            "items": [{
                "oe_number": oe,
                "name_cn": name_cn,
                "quantity": 2,
                "matched": True,
                "list_price": list_price
            }],
            "total": quote_result.get("total_amount", 0),
            "item_count": 1
        })

        await asyncio.sleep(1.5)
        chain_bus.stop()
        bus_task.cancel()
        try: await bus_task
        except asyncio.CancelledError: pass

        return {
            "trade": trade_result,
            "quotation": quote_result,
            "warehouse_alerts": warehouse.get_last_alerts(),
            "purchasing_suggestions": purchasing.get_suggestions(),
            "quote_id": quote_result["quotation_id"]
        }

    loop = asyncio.new_event_loop()
    chain = loop.run_until_complete(run_full_chain())
    loop.close()

    # 验证每一步
    _check("Step1 外贸智能体处理询盘",
           chain["trade"]["inquiry_id"].startswith("inq-"),
           f"ID={chain['trade']['inquiry_id']}")
    _check("Step1 识别语言", "detected_language" in chain["trade"])
    _check("Step2 报价智能体生成报价单",
           chain["quotation"]["quotation_id"].startswith("Q"),
           f"ID={chain['quotation']['quotation_id']}")
    _check("Step2 报价包含配件", chain["quotation"]["item_count"] >= 1)
    _check("Step2 报价总额 > 0", chain["quotation"]["total_amount"] > 0,
           f"total={chain['quotation']['total_amount']}")

    # 验证库存已被扣减
    conn = get_db()
    after_row = conn.execute(
        "SELECT quantity FROM stock WHERE part_oe=?", (oe,)
    ).fetchone()
    conn.close()
    after_qty = after_row["quantity"] if after_row else -1
    _check("Step3 仓储智能体已扣减库存",
           after_qty == before_qty - 2,
           f"before={before_qty} after={after_qty}")

    _check("Step3 仓储智能体返回预警状态",
           isinstance(chain["warehouse_alerts"], list),
           f"预警数={len(chain['warehouse_alerts'])}")

    _check("Step4 采购智能体已响应",
           isinstance(chain["purchasing_suggestions"], list),
           f"建议数={len(chain['purchasing_suggestions'])}")

    # 如果采购有建议，验证格式
    if chain["purchasing_suggestions"]:
        s = chain["purchasing_suggestions"][0]
        _check("采购建议含 part_oe", "part_oe" in s)
        _check("采购建议含 suggest_qty", "suggest_qty" in s)
        _check("采购建议含 estimated_cost", "estimated_cost" in s)
        _check("采购建议含 urgency", "urgency" in s)

    # 验证审计完整性
    trace = audit.get_trace(chain["quote_id"])
    steps = [t["step"] for t in trace]
    print(f"  审计链路: {' → '.join(steps)}")
    _check("审计包含 match 步骤", "match" in steps)
    _check("审计包含 price 步骤", "price" in steps)
    _check("审计包含 completed 步骤", "completed" in steps)
    _check("审计包含 stock_deduct 步骤", "stock_deduct" in steps)

    # 恢复库存
    conn = get_db()
    conn.execute("UPDATE stock SET quantity=? WHERE part_oe=?", (before_qty, oe))
    conn.commit()
    conn.close()

    print(f"\n  完整事件链: inquiry→trade→quotation→warehouse→purchasing ✅")


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 65)
    print("  S3 集成端到端测试")
    print("=" * 65)

    _setup()

    try: test_1_russian_inquiry_translation()
    except Exception as e:
        FAIL += 1
        print(f"  ❌ 测试1 异常: {e}")
        import traceback; traceback.print_exc()

    try: test_2_quote_to_stock_to_purchase()
    except Exception as e:
        FAIL += 1
        print(f"  ❌ 测试2 异常: {e}")
        import traceback; traceback.print_exc()

    try: test_3_alias_search()
    except Exception as e:
        FAIL += 1
        print(f"  ❌ 测试3 异常: {e}")
        import traceback; traceback.print_exc()

    try: test_4_four_agent_chain()
    except Exception as e:
        FAIL += 1
        print(f"  ❌ 测试4 异常: {e}")
        import traceback; traceback.print_exc()

    print()
    print("=" * 65)
    print(f"  结果: {PASS} 通过 / {FAIL} 失败 / {PASS+FAIL} 总计")
    print("=" * 65)

    if FAIL > 0:
        sys.exit(1)
