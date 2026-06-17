"""
擎天·API 服务 — Flask REST API (端口 3092)
给 Node.js 操作台调用的报价引擎接口
"""
import sys, os, json, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─── 健康检查 ───
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "service": "atlas-api", "version": "2.0"})

# ─── 配件搜索 ───
@app.route("/api/parts")
def search_parts():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"ok": False, "error": "缺少搜索词"})
    try:
        from core import search_parts as sp
        results = sp(q, limit=20)
        return jsonify({"ok": True, "data": results, "count": len(results)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "data": []})

# ─── 解析上传的Excel询盘 ───
@app.route("/api/parse", methods=["POST"])
def parse_inquiry():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "请上传Excel文件"})
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "文件名为空"})
    
    try:
        # 保存临时文件
        tmp_path = f"/tmp/atlas_upload_{os.getpid()}.xlsx"
        file.save(tmp_path)
        
        # 用现有的 EnTongWorkbook 解析器
        from atlas.parsers.enong_workbook import EnTongWorkbook
        wb = EnTongWorkbook(tmp_path)
        
        inquiries = wb.parse_inquiry()
        parts = wb.parse_worksheet()
        
        # 组装 items 列表（询盘 + 匹配的配件信息合并）
        items = []
        for inq in inquiries:
            item = {
                "oe_number": inq.oe_number,
                "name_cn": getattr(inq, "name_cn", ""),
                "name_ru": getattr(inq, "name_ru", ""),
                "quantity": inq.quantity,
                "matched": False
            }
            # 尝试匹配报价留底中的配件
            for p in parts:
                if getattr(p, "oe_number", "") == inq.oe_number or getattr(p, "reference_oe", "") == inq.oe_number:
                    item["list_price"] = getattr(p, "list_price", 0)
                    item["brand_channel"] = getattr(p, "brand_channel", "")
                    item["name_cn"] = getattr(p, "name_cn", "") or item["name_cn"]
                    item["matched"] = True
                    break
            items.append(item)
        
        result = {"items": items, "count": len(items)}
        
        os.remove(tmp_path)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})

# ─── 报价计算 ───
@app.route("/api/quote", methods=["POST"])
def calculate_quote():
    try:
        data = request.get_json(force=True)
        items = data.get("items", [])
        customer_id = data.get("customer_id", "")
        trade_term = data.get("trade_term", "FOB")
        payment_term = data.get("payment_term", "prepaid")
        
        if not items:
            return jsonify({"ok": False, "error": "询盘数据为空"})
        
        import asyncio
        from agents.quotation_agent import QuotationAgent
        
        agent = QuotationAgent()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            agent.process(items, customer_id, trade_term, payment_term)
        )
        loop.close()
        
        # 获取审计追踪
        from ledger.trace import audit
        trace = audit.get_trace(result["quotation_id"])
        
        return jsonify({
            "ok": result.get("ok", True),
            "data": result,
            "trace": trace,
            "revised_count": result.get("revised_count", 0),
            "audit_trail_length": result.get("audit_trail_length", len(trace)),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})

# ─── 报价对比 ───
@app.route("/api/quote/compare", methods=["POST"])
def compare_quote():
    """
    POST /api/quote/compare — 报价对比
    请求: {
        "quote_result": {...},           # process() 返回的完整报价结果
        "original_excel_path": "/path/to/报价留底.xlsx"  # 原始 Excel 路径
    }
    返回: {"ok": true, "data": {matched, diff_lines, accuracy_pct, ...}}
    """
    try:
        data = request.get_json(force=True)
        quote_result = data.get("quote_result")
        original_excel_path = data.get("original_excel_path", "")
        
        if not quote_result:
            return jsonify({"ok": False, "error": "缺少 quote_result"})
        if not original_excel_path:
            return jsonify({"ok": False, "error": "缺少 original_excel_path"})
        
        from agents.quotation_agent import QuotationAgent
        result = QuotationAgent.compare_with_original(quote_result, original_excel_path)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})

# ─── 客户列表 ───
@app.route("/api/customers")
def list_customers():
    try:
        from core import get_db
        db = get_db()
        rows = db.execute("SELECT id, name, country, region, star_level, annual_purchase FROM customers LIMIT 100").fetchall()
        customers = [dict(r) for r in rows]
        return jsonify({"ok": True, "data": customers, "count": len(customers)})
    except Exception as e:
        return jsonify({"ok": True, "data": [], "count": 0, "note": f"客户表为空: {e}"})

# ─── 规则面板 ───
@app.route("/api/rules", methods=["GET", "POST"])
def manage_rules():
    rules_path = "/srv/atlas/data/rules.md"
    if request.method == "GET":
        try:
            content = open(rules_path).read()
            from sentinel.rules_parser import parse_rules_md
            parsed = parse_rules_md(rules_path)
            return jsonify({"ok": True, "raw": content, "parsed": parsed})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    else:
        try:
            data = request.get_json(force=True)
            content = data.get("content", "")
            if content:
                # 备份旧版本
                import time, shutil
                backup = f"{rules_path}.bak.{int(time.time())}"
                if os.path.exists(rules_path):
                    shutil.copy(rules_path, backup)
                open(rules_path, "w", encoding="utf-8").write(content)
                return jsonify({"ok": True, "message": "规则已保存"})
            return jsonify({"ok": False, "error": "内容为空"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

# ─── 审计追踪 ───
@app.route("/api/trace/<quote_id>")
def get_trace(quote_id):
    from ledger.trace import audit
    trace = audit.get_trace(quote_id)
    return jsonify({"ok": True, "data": trace, "count": len(trace)})

# ─── 报价历史 ───
@app.route("/api/history")
def list_history():
    from ledger.trace import audit
    quote_ids = audit.get_all_quotes()
    return jsonify({"ok": True, "data": quote_ids, "count": len(quote_ids)})

# ─── 库存查询 ───
@app.route("/api/stock")
def get_stock_api():
    try:
        from core import get_stock
        data, alert_count = get_stock()
        return jsonify({"ok": True, "data": data, "count": len(data), "alerts": alert_count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ─── 库存预警 ───
@app.route("/api/stock/alerts")
def get_stock_alerts_api():
    try:
        from core import get_stock_alerts
        data = get_stock_alerts()
        return jsonify({"ok": True, "data": data, "count": len(data)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ─── 事件链触发（模拟报价完成 → 减库存 → 预警 → 补货建议）───
@app.route("/api/trigger-event", methods=["POST"])
def trigger_event():
    """
    模拟报价完成事件，触发完整事件链:
    报价完成 → warehouse减库存 → 低于安全线 → purchasing生成补货建议
    参数: {"items": [{"oe_number": "xxx", "quantity": N}], "quotation_id": "可选"}
    返回: 事件链结果（减库存结果 + 预警列表 + 采购建议）
    """
    try:
        data = request.get_json(force=True)
        items = data.get("items", [])
        quote_id = data.get("quotation_id", "")

        if not items:
            return jsonify({"ok": False, "error": "items 为空"})

        import asyncio
        import time
        import uuid

        if not quote_id:
            quote_id = f"EVENT-{int(time.time())}-{uuid.uuid4().hex[:6]}"

        # 构建事件
        event = {
            "id": uuid.uuid4().hex[:8],
            "event_type": "quotation.completed",
            "payload": {
                "quotation_id": quote_id,
                "items": items,
                "item_count": len(items)
            },
            "timestamp": time.time()
        }

        # 在临时 event loop 中运行事件链
        from bus.eventbus import EventBus, QUOTATION_COMPLETED
        from agents.warehouse_agent import WarehouseAgent
        from agents.purchasing_agent import PurchasingAgent

        warehouse = WarehouseAgent()
        purchasing = PurchasingAgent()

        async def run_chain():
            # 重置单例避免 event loop 绑定问题
            EventBus.reset()
            local_bus = EventBus()
            # 订阅
            local_bus.subscribe(QUOTATION_COMPLETED, warehouse.on_quotation_completed)
            local_bus.subscribe("stock.below_safety", purchasing.on_stock_low)

            # 启动总线（后台）
            local_bus._running = True
            bus_task = asyncio.create_task(local_bus.start())

            # 发布事件
            await local_bus.publish(event["event_type"], event["payload"])

            # 等待处理完成（最多3秒）
            await asyncio.sleep(1.5)

            # 停止总线
            local_bus.stop()
            bus_task.cancel()
            try:
                await bus_task
            except asyncio.CancelledError:
                pass

            return {
                "warehouse_alerts": warehouse.get_last_alerts(),
                "purchasing_suggestions": purchasing.get_suggestions()
            }

        loop = asyncio.new_event_loop()
        chain_result = loop.run_until_complete(run_chain())
        loop.close()

        # 返回完整事件链结果
        return jsonify({
            "ok": True,
            "event_id": event["id"],
            "quotation_id": quote_id,
            "chain": {
                "step1_deducted": len(items),
                "step2_alerts": len(chain_result["warehouse_alerts"]),
                "step3_suggestions": len(chain_result["purchasing_suggestions"]),
                "alerts": chain_result["warehouse_alerts"],
                "suggestions": chain_result["purchasing_suggestions"]
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


# ─── 智能体状态 ───
@app.route("/api/agents/status")
def agents_status():
    """返回所有智能体的运行状态"""
    try:
        from agents.warehouse_agent import WarehouseAgent
        from agents.purchasing_agent import PurchasingAgent

        warehouse = WarehouseAgent()
        purchasing = PurchasingAgent()

        agents = [
            {
                "name": warehouse.name,
                "status": warehouse.status,
                "type": "warehouse",
                "description": "仓储智能体 - 管理库存，响应报价事件减库存"
            },
            {
                "name": purchasing.name,
                "status": purchasing.status,
                "type": "purchasing",
                "description": "采购智能体 - 监听库存预警，生成补货建议"
            }
        ]

        return jsonify({
            "ok": True,
            "agents": agents,
            "count": len(agents)
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════ 别名映射 API ═══════════

@app.route("/api/aliases")
def search_aliases():
    """GET /api/aliases?q=xxx — 搜索别名（FTS5 + 别名表）"""
    q = request.args.get("q", "")
    limit = request.args.get("limit", 5, type=int)
    if not q:
        return jsonify({"ok": False, "error": "缺少搜索词 q"})
    try:
        from core.aliases import search_alias
        results = search_alias(q, limit=limit)
        return jsonify({"ok": True, "data": results, "count": len(results)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "data": []})


@app.route("/api/aliases/suggest", methods=["POST"])
def suggest_aliases():
    """
    POST /api/aliases/suggest — AI 建议
    Body: {"new_name": "...", "oe_number": "..."}
    返回：候选配件列表（可能是别名映射）
    """
    try:
        data = request.get_json(force=True)
        new_name = data.get("new_name", "")
        oe_number = data.get("oe_number", "")
        if not new_name and not oe_number:
            return jsonify({"ok": False, "error": "至少提供 new_name 或 oe_number"})
        from core.aliases import suggest_alias
        candidates = suggest_alias(new_name, oe_number)
        return jsonify({"ok": True, "data": candidates, "count": len(candidates)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "data": []})


@app.route("/api/aliases/confirm", methods=["POST"])
def confirm_alias_api():
    """
    POST /api/aliases/confirm — 人工确认别名
    Body: {"alias_id": N} 或 {"part_id": N, "alias_text": "...", "lang": "zh"}
    如果是新增+确认：传入 part_id + alias_text，会自动创建并确认
    """
    try:
        data = request.get_json(force=True)
        from core.aliases import add_alias, confirm_alias, get_aliases

        alias_id = data.get("alias_id")
        if alias_id:
            # 直接确认已有别名
            result = confirm_alias(int(alias_id))
            if result:
                return jsonify({"ok": True, "data": result, "message": "别名已确认"})
            else:
                return jsonify({"ok": False, "error": f"别名 id={alias_id} 不存在"})

        part_id = data.get("part_id")
        alias_text = data.get("alias_text")
        if part_id and alias_text:
            lang = data.get("lang", "zh")
            # 创建并直接确认
            alias = add_alias(int(part_id), alias_text, lang, confirmed=True)
            return jsonify({"ok": True, "data": alias, "message": "别名已创建并确认"})

        return jsonify({"ok": False, "error": "请提供 alias_id 或 (part_id + alias_text)"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/aliases/<int:part_id>", methods=["GET"])
def get_part_aliases(part_id):
    """GET /api/aliases/<part_id> — 获取某配件的所有别名"""
    try:
        confirmed_only = request.args.get("confirmed_only", "0") == "1"
        from core.aliases import get_aliases
        aliases = get_aliases(part_id, confirmed_only=confirmed_only)
        return jsonify({"ok": True, "data": aliases, "count": len(aliases)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "data": []})


@app.route("/api/aliases/unconfirmed", methods=["GET"])
def get_unconfirmed():
    """GET /api/aliases/unconfirmed — 获取所有待确认的 AI 建议别名"""
    try:
        from core.aliases import get_unconfirmed_aliases
        aliases = get_unconfirmed_aliases()
        return jsonify({"ok": True, "data": aliases, "count": len(aliases)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "data": []})


# ─── 翻译接口 ───
@app.route("/api/translate", methods=["POST"])
def translate_text():
    """POST /api/translate — 翻译询盘文本
    请求: {"text": "...", "source_lang": "ru", "target_lang": "zh"}
    返回: {"ok": true, "translated": "..."}
    """
    try:
        data = request.get_json(force=True)
        text = data.get("text", "")
        source_lang = data.get("source_lang", "auto")
        target_lang = data.get("target_lang", "zh")

        if not text.strip():
            return jsonify({"ok": False, "error": "文本为空"})

        from oracle.client import translate as do_translate
        result = do_translate(text, target_lang=target_lang, source_lang=source_lang)

        return jsonify({"ok": True, "translated": result, "source_lang": source_lang, "target_lang": target_lang})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


# ─── PI 生成接口 ───
@app.route("/api/pi/generate", methods=["POST"])
def generate_pi():
    """POST /api/pi/generate — 根据报价结果生成 PI 草稿
    请求: {
        "inquiry_text": "原文询盘",
        "items": [{"oe_number":"xxx","name":"xxx","quantity":1,"unit_price":100,"total":500}],
        "customer_name": "客户名",
        "trade_term": "FOB",
        "payment_term": "prepaid",
        "currency": "USD"
    }
    返回: {"ok": true, "pi_draft": "..."}
    """
    try:
        data = request.get_json(force=True)
        inquiry_text = data.get("inquiry_text", "")
        items = data.get("items", [])
        customer_name = data.get("customer_name", "")
        trade_term = data.get("trade_term", "FOB")
        payment_term = data.get("payment_term", "prepaid")
        currency = data.get("currency", "USD")

        if not items:
            return jsonify({"ok": False, "error": "items 为空"})

        from oracle.client import generate_pi as do_generate_pi
        pi_draft = do_generate_pi(
            inquiry_text=inquiry_text,
            items=items,
            customer_name=customer_name,
            trade_term=trade_term,
            payment_term=payment_term,
            currency=currency,
        )

        return jsonify({"ok": True, "pi_draft": pi_draft})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


# ─── 询盘处理（翻译+提取+PI一体化）───
@app.route("/api/inquiry/process", methods=["POST"])
def process_inquiry():
    """POST /api/inquiry/process — 一站式询盘处理
    请求: {"text": "俄文/英文询盘", "language": "ru", "customer": "客户名"}
    返回: {"ok": true, "data": {translated_text, extracted_items, pi_draft}}
    """
    try:
        data = request.get_json(force=True)
        text = data.get("text", "")
        lang = data.get("language", "auto")
        customer = data.get("customer", "")

        if not text.strip():
            return jsonify({"ok": False, "error": "询盘文本为空"})

        import asyncio
        from agents.trade_agent import trade_agent

        # Build event
        event = {
            "id": f"API-INQUIRY-{id(text)}",
            "event_type": "inquiry.received",
            "payload": {
                "text": text,
                "language": lang,
                "customer": customer,
            }
        }

        # Run synchronously
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(trade_agent.on_inquiry(event))
        loop.close()

        return jsonify({"ok": True, "data": result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", "sk-f4aef21293b5472d9f22f86ad289b573")
    port = int(os.environ.get("ATLAS_API_PORT", 3095))
    print(f"🚀 元策·擎天 API 启动 :{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
