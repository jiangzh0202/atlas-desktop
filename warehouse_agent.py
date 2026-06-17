"""
仓储智能体 (P1) — 真实数据联动
订阅报价完成 → SQLite减库存 → 低于安全线发预警 → 审计日志
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.eventbus import EventBus, STOCK_BELOW_SAFETY, QUOTATION_COMPLETED
from ledger.trace import audit

class WarehouseAgent:
    def __init__(self):
        self.name = "warehouse"
        self.status = "idle"
        self._last_alerts = []
        self._alert_cache = []      # 缓存最近一次预警结果
    
    async def on_quotation_completed(self, event: dict):
        """报价完成 → 减库存"""
        bus = EventBus()  # 动态获取当前单例
        payload = event.get("payload", {})
        items = payload.get("items", [])
        quote_id = payload.get("quotation_id", "") or event.get("id", "unknown")

        self.status = "processing"
        alerts = []
        deducted = []

        from core import get_db
        conn = get_db()

        try:
            for item in items:
                oe = item.get("oe_number", "")
                qty = item.get("quantity", 0)
                if not oe or qty <= 0:
                    continue

                # 查当前库存
                row = conn.execute(
                    "SELECT quantity, safety_line FROM stock WHERE part_oe=?",
                    (oe,)
                ).fetchone()

                if not row:
                    # 未在库存表中，跳过
                    audit.log(quote_id, "stock_deduct", "warehouse",
                              input_data={"oe": oe, "qty": qty},
                              output_data={"result": "not_in_stock"},
                              notes="配件不在库存表中")
                    continue

                current_qty, safety_line = row["quantity"], row["safety_line"]
                new_qty = max(0, current_qty - qty)

                # 更新库存
                conn.execute(
                    "UPDATE stock SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE part_oe=?",
                    (new_qty, oe)
                )
                deducted.append({"oe": oe, "before": current_qty, "after": new_qty, "deducted": qty})

                # 审计
                audit.log(quote_id, "stock_deduct", "warehouse",
                          input_data={"oe": oe, "qty_deducted": qty},
                          output_data={"before": current_qty, "after": new_qty, "safety": safety_line})

                # 低于安全线 → 发预警
                if new_qty <= safety_line:
                    alert_payload = {
                        "part_oe": oe,
                        "name_cn": item.get("name_cn", ""),
                        "current": new_qty,
                        "safety": safety_line,
                        "quotation_id": payload.get("quotation_id", quote_id)
                    }
                    await bus.publish(STOCK_BELOW_SAFETY, alert_payload)
                    try:
                        from ws_server import publish_ws
                        publish_ws(STOCK_BELOW_SAFETY, alert_payload)
                    except Exception:
                        pass
                    alerts.append(alert_payload)

                    audit.log(quote_id, "stock_alert", "warehouse",
                              input_data={"oe": oe, "current": new_qty, "safety": safety_line},
                              decision="ALERT",
                              notes=f"库存 {new_qty} <= 安全线 {safety_line}")

            conn.commit()
            self._alert_cache = alerts

            if alerts:
                print(f"[仓储智能体] 库存预警 {len(alerts)} 条: {[a['part_oe'] for a in alerts]}")
            if deducted:
                print(f"[仓储智能体] 减库存 {len(deducted)} 条")

        except Exception as e:
            conn.rollback()
            print(f"[仓储智能体] 错误: {e}")
            audit.log(quote_id, "stock_error", "warehouse",
                      notes=f"减库存异常: {e}")
        finally:
            conn.close()
            self.status = "idle"

    def get_last_alerts(self) -> list:
        return self._alert_cache

    async def start(self):
        bus.subscribe(QUOTATION_COMPLETED, self.on_quotation_completed)
        self.status = "idle"
        print(f"[仓储智能体] 已启动，监控库存 (SQLite stock 表)")
