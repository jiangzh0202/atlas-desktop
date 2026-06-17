"""
报价智能体 — 核心智能体 (P0)
询盘→匹配→算价→审核→报价单→事件
"""
import uuid, time, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.eventbus import bus, QUOTATION_COMPLETED
from ledger.trace import audit

class QuotationAgent:
    """报价智能体。不继承 BaseAgent，独立实现以便快速迭代。"""
    
    def __init__(self):
        self.name = "quotation"
        self.status = "idle"
    
    async def process(self, inquiry_items: list, customer_id: str = None, 
                      trade_term: str = "FOB", payment_term: str = "prepaid") -> dict:
        """完整报价流程"""
        self.status = "running"
        quote_id = f"Q{int(time.time())}"
        
        # Step 1: 匹配配件（优先用 parse 已匹配的数据）
        matched_items = []
        for item in inquiry_items:
            oe = item.get("oe_number", "")
            part_name = item.get("name_cn", "") or item.get("name_ru", "")
            qty = item.get("quantity", 1)
            already_matched = item.get("matched", False)
            list_price = item.get("list_price", 0)
            brand = item.get("brand_channel", "")
            is_matched = False
            
            if already_matched and list_price > 0:
                matched = {
                    "oe_number": oe, "name_cn": part_name, "quantity": qty,
                    "list_price": list_price, "brand_channel": brand, "matched": True
                }
                is_matched = True
            else:
                part = None
                try:
                    from core import get_part_by_oe
                    part = get_part_by_oe(oe)
                except: pass
                
                if part:
                    matched = {
                        "oe_number": oe,
                        "name_cn": getattr(part, "name_cn", part_name),
                        "quantity": qty,
                        "list_price": getattr(part, "list_price", 0),
                        "brand_channel": getattr(part, "brand_channel", ""),
                        "matched": True
                    }
                    is_matched = True
                else:
                    matched = {
                        "oe_number": oe, "name_cn": part_name, "quantity": qty,
                        "list_price": 0, "matched": False, "confidence": "low"
                    }
            matched_items.append(matched)
            
            audit.log(quote_id, "match", "quotation", 
                      input_data={"oe": oe, "name": part_name},
                      output_data={"matched": is_matched})
        
        # Step 2: 算价
        priced_items = []
        total_amount = 0
        for item in matched_items:
            if not item["matched"]:
                item["unit_price"] = 0
                item["total_amount"] = 0
                priced_items.append(item)
                continue
            
            # 调 forge 算价
            try:
                from forge import calculate_line_price
                result = calculate_line_price(item, item["quantity"])
                item["unit_price"] = result.get("unit_price", 0)
                item["total_amount"] = result.get("total_amount", 0)
                item["pricing_mode"] = result.get("mode", "STANDARD")
                item["trace"] = result.get("trace", [])
            except Exception as e:
                item["unit_price"] = item["list_price"]
                item["total_amount"] = item["list_price"] * item["quantity"]
                item["pricing_mode"] = "FALLBACK"
                item["trace"] = [f"错误: {e}"]
            
            total_amount += item["total_amount"]
            priced_items.append(item)
            
            audit.log(quote_id, "price", "quotation",
                      input_data={"oe": item["oe_number"], "qty": item["quantity"]},
                      output_data={"price": item["unit_price"], "total": item["total_amount"]})
        
        # Step 3: 检查底线
        warnings = []
        try:
            from sentinel import check_price_floor
            for item in priced_items:
                if item["matched"]:
                    ok = check_price_floor(item["unit_price"], 0)  # 简化
                    if not ok:
                        warnings.append(f"{item['oe_number']}: 低于底线")
                        audit.log(quote_id, "floor_check", "sentinel",
                                  decision="WARN",
                                  notes=f"{item['oe_number']} below floor")
        except Exception as e:
            warnings.append(f"底线检查异常: {e}")
        
        # Step 4: 确定审核人
        approver = "报价员"
        if total_amount > 200000:
            approver = "老板"
        elif total_amount > 50000:
            approver = "主管"
        
        result = {
            "quotation_id": quote_id,
            "customer_id": customer_id,
            "trade_term": trade_term,
            "payment_term": payment_term,
            "items": priced_items,
            "total_amount": total_amount,
            "item_count": len(priced_items),
            "warnings": warnings,
            "approver": approver,
            "human_approval_required": True,
            "status": "pending_approval"
        }
        
        # Step 5: 发布事件
        await bus.publish(QUOTATION_COMPLETED, {
            "quotation_id": quote_id,
            "items": priced_items,
            "total": total_amount,
            "item_count": len(priced_items)
        })
        
        audit.log(quote_id, "completed", "quotation",
                  output_data={"total": total_amount, "approver": approver})
        
        self.status = "waiting_human"
        return result
