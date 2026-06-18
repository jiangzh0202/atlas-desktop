"""
采购智能体 (P1) — 真实数据联动
订阅库存预警 → 从 parts 表查 list_price → 生成补货建议 → 审计日志
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.eventbus import EventBus, STOCK_BELOW_SAFETY
from ledger.trace import audit

class PurchasingAgent:
    def __init__(self):
        self.name = "purchasing"
        self.status = "idle"
        self._suggestions = []  # 本轮补货建议

    async def on_stock_low(self, event: dict):
        """收到库存预警 → 查配件价格 → 生成补货建议"""
        payload = event.get("payload", {})
        part_oe = payload.get("part_oe", "")
        name_cn = payload.get("name_cn", "")
        current = payload.get("current", 0)
        safety = payload.get("safety", 0)
        quote_id = payload.get("quotation_id", event.get("id", "unknown"))

        self.status = "processing"

        # 建议采购量: safety_line × 2 - current（确保补到安全线的2倍缓冲）
        suggest_qty = max(0, safety * 2 - current)

        # 从 parts 表查牌价
        list_price = 0.0
        brand_channel = ""
        try:
            from core import get_db
            conn = get_db()
            row = conn.execute(
                "SELECT list_price, brand_channel, name_cn FROM parts WHERE oe_number=?",
                (part_oe,)
            ).fetchone()
            conn.close()
            if row:
                list_price = row["list_price"] or 0.0
                brand_channel = row["brand_channel"] or ""
                if not name_cn:
                    name_cn = row["name_cn"] or ""
        except Exception as e:
            print(f"[采购智能体] 查配件价格失败: {e}")

        estimated_cost = round(list_price * suggest_qty, 2)

        suggestion = {
            "part_oe": part_oe,
            "name_cn": name_cn,
            "brand_channel": brand_channel,
            "list_price": list_price,
            "current_stock": current,
            "safety_line": safety,
            "suggest_qty": suggest_qty,
            "estimated_cost": estimated_cost,
            "urgency": "high" if current <= safety * 0.5 else "normal",
            "needs_approval": True,
            "agent": self.name
        }

        self._suggestions.append(suggestion)

        # 审计
        audit.log(quote_id, "purchase_suggest", "purchasing",
                  input_data={"part_oe": part_oe, "current": current, "safety": safety},
                  output_data={"suggest_qty": suggest_qty, "estimated_cost": estimated_cost},
                  decision="SUGGEST",
                  notes=f"建议补货 {suggest_qty} 件, 预估成本 ¥{estimated_cost}")

        print(f"[采购智能体] 补货建议: {part_oe} 库存{current}<安全线{safety} → 建议采购{suggest_qty}件 预估¥{estimated_cost}")

        self.status = "idle"
        return suggestion

    def get_suggestions(self) -> list:
        return self._suggestions

    def clear_suggestions(self):
        self._suggestions = []

    async def start(self):
        bus.subscribe(STOCK_BELOW_SAFETY, self.on_stock_low)
        self.status = "idle"
        print(f"[采购智能体] 已启动，监听 {STOCK_BELOW_SAFETY}")
