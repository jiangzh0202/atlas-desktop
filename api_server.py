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
        results, total = sp(q, limit=20)
        return jsonify({"ok": True, "data": results, "count": total})
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


# ─── 报价 Excel 导出 ───
@app.route("/api/quote/<quote_id>/export")
def export_quote_excel(quote_id):
    """
    GET /api/quote/<quote_id>/export — 导出报价单为 Excel
    返回 .xlsx 文件，可直接发客户
    """
    try:
        from ledger.trace import audit
        trace = audit.get_trace(quote_id)
        if not trace:
            return jsonify({"ok": False, "error": f"报价 {quote_id} 不存在"})

        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
        from openpyxl.utils import get_column_letter
        import io

        wb = Workbook()
        ws = wb.active
        ws.title = "报价单"

        # ─── 样式 ───
        header_font = Font(name="Microsoft YaHei", bold=True, size=11, color="FFFFFF")
        header_fill = PatternFill(start_color="7ECF5E", end_color="7ECF5E", fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        body_font = Font(name="Microsoft YaHei", size=10)
        body_align = Alignment(horizontal="center", vertical="center")
        money_fmt = '#,##0.00'
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )
        total_font = Font(name="Microsoft YaHei", bold=True, size=12)

        # ─── 标题行 ───
        ws.merge_cells('A1:G1')
        title_cell = ws['A1']
        title_cell.value = f"报价单 — {quote_id}"
        title_cell.font = Font(name="Microsoft YaHei", bold=True, size=14, color="1A1A2E")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 30

        # ─── 表头 ───
        headers = ["序号", "OE号", "品名", "品牌", "数量", "单价", "小计"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=2, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        # ─── 从审计日志重建 items（match.name + price.price/total）───
        match_map = {}   # oe → {name}
        price_items = [] # [{oe, qty, price, total}]
        for entry in trace:
            if entry.get("step") == "match":
                inp = entry.get("input", {})
                oe = inp.get("oe", "").strip()
                if oe:
                    match_map[oe] = inp.get("name", "")
            elif entry.get("step") == "price":
                inp = entry.get("input", {})
                out = entry.get("output", {})
                oe = inp.get("oe", "").strip()
                if oe and out.get("price", 0):
                    price_items.append({
                        "oe": oe,
                        "qty": inp.get("qty", 1),
                        "price": out.get("price", 0),
                        "total": out.get("total", 0),
                    })

        if not price_items:
            return jsonify({
                "ok": False,
                "error": "该报价无明细数据，无法导出。建议重新计算报价后导出。"
            })

        # ─── 数据行 ───
        total_amount = 0
        row = 3
        for i, item in enumerate(price_items, 1):
            oe = item.get("oe", "")
            name = match_map.get(oe, "")
            qty = item.get("qty", 1)
            price = item.get("price", 0)
            subtotal = item.get("total", 0)
            brand = ""  # 审计日志暂不记录 brand

            ws.cell(row=row, column=1, value=i).font = body_font
            ws.cell(row=row, column=1).alignment = body_align
            ws.cell(row=row, column=1).border = thin_border

            ws.cell(row=row, column=2, value=oe).font = body_font
            ws.cell(row=row, column=2).alignment = body_align
            ws.cell(row=row, column=2).border = thin_border

            ws.cell(row=row, column=3, value=name).font = body_font
            ws.cell(row=row, column=3).alignment = Alignment(horizontal="left", vertical="center")
            ws.cell(row=row, column=3).border = thin_border

            ws.cell(row=row, column=4, value=brand).font = body_font
            ws.cell(row=row, column=4).alignment = body_align
            ws.cell(row=row, column=4).border = thin_border

            ws.cell(row=row, column=5, value=int(qty)).font = body_font
            ws.cell(row=row, column=5).alignment = body_align
            ws.cell(row=row, column=5).border = thin_border

            price_cell = ws.cell(row=row, column=6, value=float(price))
            price_cell.font = body_font
            price_cell.alignment = body_align
            price_cell.number_format = money_fmt
            price_cell.border = thin_border

            subtotal_cell = ws.cell(row=row, column=7, value=float(subtotal))
            subtotal_cell.font = body_font
            subtotal_cell.alignment = body_align
            subtotal_cell.number_format = money_fmt
            subtotal_cell.border = thin_border

            total_amount += float(subtotal)
            ws.row_dimensions[row].height = 22
            row += 1

        total_amount = round(total_amount, 2)  # 修正浮点累积误差

        # ─── 合计行 ───
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        total_label = ws.cell(row=row, column=1, value="合计")
        total_label.font = total_font
        total_label.alignment = Alignment(horizontal="right", vertical="center")
        total_label.border = thin_border
        for c in range(2, 6):
            ws.cell(row=row, column=c).border = thin_border

        total_cell = ws.cell(row=row, column=6, value=total_amount)
        total_cell.font = total_font
        total_cell.alignment = body_align
        total_cell.number_format = money_fmt
        total_cell.border = thin_border

        ws.cell(row=row, column=7).border = thin_border
        ws.row_dimensions[row].height = 26

        # ─── 列宽 ───
        ws.column_dimensions['A'].width = 6
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 32
        ws.column_dimensions['D'].width = 14
        ws.column_dimensions['E'].width = 8
        ws.column_dimensions['F'].width = 14
        ws.column_dimensions['G'].width = 14

        # ─── 输出 ───
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"报价单_{quote_id}.xlsx"
        )
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
    """返回完整报价历史（含金额/日期/配件数/状态）"""
    try:
        from core import get_db
        conn = get_db()
        quotes = conn.execute("""
            SELECT q.id, q.created_at, q.total_amount, q.status,
                   q.customer_name, q.trade_term, q.payment_term,
                   COUNT(ql.id) as line_count
            FROM quotations q
            LEFT JOIN quotation_lines ql ON ql.quotation_id = q.id
            GROUP BY q.id
            ORDER BY q.created_at DESC
            LIMIT 50
        """).fetchall()
        conn.close()

        data = []
        for q in quotes:
            data.append({
                "id": q["id"],
                "created_at": q["created_at"] or "",
                "total_amount": q["total_amount"] or 0,
                "item_count": q["line_count"] or 0,
                "status": q["status"] or "draft",
                "customer_name": q["customer_name"] or "",
                "trade_term": q["trade_term"] or "",
                "payment_term": q["payment_term"] or "",
                "line_count": q["line_count"] or 0,
            })

        # 回退：如果 quotations 表为空，用审计日志
        if not data:
            from ledger.trace import audit
            quote_ids = audit.get_all_quotes()
            data = [{"id": qid, "created_at": "", "total_amount": 0,
                     "item_count": 0, "status": "archived",
                     "customer_name": "", "trade_term": "", "payment_term": "",
                     "line_count": 0} for qid in quote_ids]

        return jsonify({"ok": True, "data": data, "count": len(data)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})

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
            try:
                from ws_server import publish_ws
                publish_ws(event["event_type"], event["payload"])
            except Exception:
                pass

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




# ─── 价格变更接口 ───
@app.route("/api/price/update", methods=["POST"])
def update_price():
    """POST /api/price/update — 更新配件价格并发布 price.changed 事件
    请求: {"oe_number": "PART-0001", "new_price": 4500.00, "brand": "A2080"}
    返回: {"ok": true, "data": {...}, "event_id": "..."}
    """
    try:
        data = request.get_json(force=True)
        oe_number = data.get("oe_number", "").strip()
        new_price = data.get("new_price")
        brand = data.get("brand", "").strip()

        if not oe_number:
            return jsonify({"ok": False, "error": "缺少 oe_number"})
        if new_price is None:
            return jsonify({"ok": False, "error": "缺少 new_price"})
        try:
            new_price = float(new_price)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "new_price 必须是数字"})

        from core import get_db, get_part_by_oe
        import asyncio
        import time
        import uuid

        # 1) 更新 parts 表
        db = get_db()
        # 先查旧值
        old = db.execute(
            "SELECT oe_number, list_price, brand_channel, cost_with_tax FROM parts WHERE oe_number = ?",
            (oe_number,)
        ).fetchone()

        if not old:
            db.close()
            return jsonify({"ok": False, "error": f"配件 {oe_number} 不存在"})

        old_price = old["list_price"]
        old_brand = old["brand_channel"]
        cost_with_tax = old["cost_with_tax"] or 0.0

        # 更新价格
        if brand:
            db.execute(
                "UPDATE parts SET list_price = ?, brand_channel = ? WHERE oe_number = ?",
                (new_price, brand, oe_number)
            )
        else:
            db.execute(
                "UPDATE parts SET list_price = ? WHERE oe_number = ?",
                (new_price, oe_number)
            )
        db.commit()
        db.close()

        # 2) 发布 price.changed 事件
        event = {
            "id": uuid.uuid4().hex[:8],
            "event_type": "price.changed",
            "payload": {
                "oe_number": oe_number,
                "old_price": old_price,
                "new_price": new_price,
                "brand": brand or old_brand,
                "cost_with_tax": cost_with_tax,
            },
            "timestamp": time.time()
        }

        # 在临时 event loop 中执行
        from bus.eventbus import EventBus, PRICE_CHANGED

        async def run_price_change():
            EventBus.reset()
            local_bus = EventBus()

            # 导入并注册 price.changed handler
            from bus.handlers import on_price_changed
            local_bus.subscribe(PRICE_CHANGED, on_price_changed)

            local_bus._running = True
            bus_task = asyncio.create_task(local_bus.start())

            await local_bus.publish(event["event_type"], event["payload"])
            try:
                from ws_server import publish_ws
                publish_ws(event["event_type"], event["payload"])
            except Exception:
                pass
            await asyncio.sleep(0.5)  # 等待异步处理

            local_bus.stop()
            bus_task.cancel()
            try:
                await bus_task
            except asyncio.CancelledError:
                pass

        loop = asyncio.new_event_loop()
        loop.run_until_complete(run_price_change())
        loop.close()

        return jsonify({
            "ok": True,
            "data": {
                "oe_number": oe_number,
                "old_price": old_price,
                "new_price": new_price,
                "brand": brand or old_brand,
            },
            "event_id": event["id"],
            "message": "价格已更新，price.changed 事件已发布"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})

# ─── 首页看板 ───
@app.route("/api/dashboard")
def dashboard():
    """返回首页看板数据：核心指标 + 库存预警 + 最近活动"""
    try:
        from core import get_db
        from ledger.trace import audit
        conn = get_db()

        # 核心指标
        parts_count = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
        stock_count = conn.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
        alert_count = conn.execute(
            "SELECT COUNT(*) FROM stock WHERE quantity <= safety_line"
        ).fetchone()[0]
        brands = conn.execute(
            "SELECT COUNT(DISTINCT brand_channel) FROM parts WHERE brand_channel != ''"
        ).fetchone()[0]
        pricing_modes = conn.execute(
            "SELECT pricing_mode, COUNT(*) as cnt FROM parts "
            "GROUP BY pricing_mode ORDER BY cnt DESC"
        ).fetchall()

        # 最近报价
        recent_quotes = conn.execute("""
            SELECT q.id, q.created_at, q.total_amount, q.status, q.customer_name,
                   COUNT(ql.id) as line_count
            FROM quotations q
            LEFT JOIN quotation_lines ql ON ql.quotation_id = q.id
            GROUP BY q.id
            ORDER BY q.created_at DESC LIMIT 5
        """).fetchall()

        # 库存预警列表
        alerts = conn.execute("""
            SELECT s.part_oe, s.quantity, s.safety_line, p.name_cn, p.brand_channel, p.list_price
            FROM stock s LEFT JOIN parts p ON s.part_oe = p.oe_number
            WHERE s.quantity <= s.safety_line
            ORDER BY (s.safety_line - s.quantity) DESC
            LIMIT 10
        """).fetchall()

        conn.close()

        # 最近活动（从审计日志）
        trace_ids = audit.get_all_quotes()
        recent_activity = trace_ids[:10] if trace_ids else []

        return jsonify({"ok": True, "data": {
            "stats": {
                "parts": parts_count,
                "stock": stock_count,
                "alerts": alert_count,
                "brands": brands,
                "modes": [{"mode": m[0], "count": m[1]} for m in pricing_modes],
            },
            "recent_quotes": [{
                "id": q["id"], "created_at": q["created_at"] or "",
                "total_amount": q["total_amount"] or 0,
                "item_count": q["line_count"] or 0,
                "status": q["status"] or "draft",
                "customer_name": q["customer_name"] or "",
            } for q in recent_quotes],
            "stock_alerts": [{
                "part_oe": a["part_oe"], "name_cn": a["name_cn"] or "",
                "quantity": a["quantity"], "safety_line": a["safety_line"],
                "brand": a["brand_channel"] or "",
                "list_price": a["list_price"] or 0,
                "gap": a["safety_line"] - a["quantity"],
            } for a in alerts],
            "recent_activity": recent_activity,
        }})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", "sk-f4aef21293b5472d9f22f86ad289b573")
    port = int(os.environ.get("ATLAS_API_PORT", 3095))

    # ─── 启动 WebSocket 事件推送服务 :3096 ───
    try:
        from ws_server import start_ws_in_thread
        ws_port = int(os.environ.get("ATLAS_WS_PORT", 3096))
        start_ws_in_thread(port=ws_port)
        print(f"🔌 WebSocket 事件推送已启动 ws://0.0.0.0:{ws_port}")
    except Exception as e:
        print(f"[warn] WebSocket 启动失败（非致命）: {e}")

    print(f"🚀 元策·擎天 API 启动 :{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
