"""
报价智能体 — 核心智能体 (P0)
询盘→匹配→算价→审核→报价单→事件

状态机: idle → running → waiting_human → approved / rejected → revised → (循环)
"""
import uuid, time, sys, json, copy
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.eventbus import bus, QUOTATION_COMPLETED
from ledger.trace import audit

# ─── 状态机定义 ───
VALID_TRANSITIONS = {
    "idle":            ["running"],
    "running":         ["waiting_human", "error"],
    "waiting_human":   ["approved", "rejected"],
    "approved":        [],            # 终态
    "rejected":        ["running"],   # 拒绝后可修订重新报价
    "error":           ["idle"],      # 错误后可重置
}

class QuotationAgent:
    """报价智能体。不继承 BaseAgent，独立实现以便快速迭代。"""
    
    def __init__(self):
        self.name = "quotation"
        self._status = "idle"
        self._last_result = None       # 最后一次报价结果
        self._revised_count = 0        # 修订次数
    
    # ─── 状态管理 ───
    @property
    def status(self) -> str:
        return self._status
    
    def _transition(self, new_status: str):
        """状态转移，含合法性校验"""
        allowed = VALID_TRANSITIONS.get(self._status, [])
        if new_status not in allowed:
            raise ValueError(
                f"非法状态转移: {self._status} → {new_status}，"
                f"允许的目标: {allowed}"
            )
        self._status = new_status
    
    # ─── 输入校验 ───
    @staticmethod
    def _validate_input(inquiry_items: list) -> Optional[dict]:
        """
        校验报价输入，返回结构化错误或 None（通过）。
        {"ok": false, "step": "validation", "error": "..."}
        """
        if not isinstance(inquiry_items, list):
            return {"ok": False, "step": "validation", "error": "items 必须是 list 类型"}
        if len(inquiry_items) == 0:
            return {"ok": False, "step": "validation", "error": "询盘数据为空 (items=[])"}
        
        # 逐项检查是否含有 oe_number
        missing_oe = []
        for i, item in enumerate(inquiry_items):
            if not isinstance(item, dict):
                return {"ok": False, "step": "validation",
                        "error": f"items[{i}] 不是 dict 类型"}
            oe = item.get("oe_number", "")
            if not oe or not str(oe).strip():
                missing_oe.append(i)
        
        if missing_oe:
            return {
                "ok": False,
                "step": "validation",
                "error": f"以下 items 缺少 oe_number: 索引 {missing_oe}",
                "detail": {"missing_indices": missing_oe}
            }
        
        return None  # 校验通过
    
    # ─── 主流程 ───
    async def process(self, inquiry_items: list, customer_id: str = None,
                      trade_term: str = "FOB", payment_term: str = "prepaid") -> dict:
        """完整报价流程，每步返回结构化结果"""
        created_at = time.time()
        
        # Step 0: 状态转移
        try:
            self._transition("running")
        except ValueError as e:
            return {"ok": False, "step": "status", "error": str(e)}
        
        # Step 0.5: 输入校验
        validation_error = self._validate_input(inquiry_items)
        if validation_error:
            self._transition("error")
            return validation_error
        
        quote_id = f"Q{int(created_at)}"
        
        # ── Step 1: 匹配配件 ──
        matched_items = []
        for item in inquiry_items:
            oe = str(item.get("oe_number", "")).strip()
            part_name = item.get("name_cn", "") or item.get("name_ru", "")
            qty = item.get("quantity", 1)
            already_matched = item.get("matched", False)
            list_price = item.get("list_price", 0)
            brand = item.get("brand_channel", "")
            is_matched = False
            
            try:
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
                    except ImportError:
                        pass
                    except Exception as e:
                        # 匹配子步骤错误不打乱整体，记录后继续
                        audit.log(quote_id, "match_error", "quotation",
                                  input_data={"oe": oe},
                                  notes=f"get_part_by_oe 异常: {e}")
                    
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
            except Exception as e:
                # 单行匹配异常不应中断整个报价
                matched = {
                    "oe_number": oe, "name_cn": part_name, "quantity": qty,
                    "list_price": 0, "matched": False,
                    "match_error": str(e)
                }
            
            matched_items.append(matched)
            
            audit.log(quote_id, "match", "quotation",
                      input_data={"oe": oe, "name": part_name},
                      output_data={"matched": is_matched})
        
        # ── Step 2: 算价 ──
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
            except ImportError:
                item["unit_price"] = item["list_price"]
                item["total_amount"] = item["list_price"] * item["quantity"]
                item["pricing_mode"] = "FALLBACK"
                item["trace"] = ["forge 模块不可用，使用牌价兜底"]
            except Exception as e:
                item["unit_price"] = item["list_price"]
                item["total_amount"] = item["list_price"] * item["quantity"]
                item["pricing_mode"] = "FALLBACK"
                item["trace"] = [f"算价错误: {e}"]
            
            total_amount += item["total_amount"]
            priced_items.append(item)
            
            audit.log(quote_id, "price", "quotation",
                      input_data={"oe": item["oe_number"], "qty": item["quantity"]},
                      output_data={"price": item["unit_price"], "total": item["total_amount"]})
        
        # ── Step 3: 检查底线 ──
        warnings = []
        try:
            from sentinel import check_price_floor
            for item in priced_items:
                if item.get("matched"):
                    ok = check_price_floor(item["unit_price"], 0)
                    if not ok:
                        warnings.append(f"{item['oe_number']}: 低于底线")
                        audit.log(quote_id, "floor_check", "sentinel",
                                  decision="WARN",
                                  notes=f"{item['oe_number']} below floor")
        except ImportError:
            # sentinel 模块不存在时不阻塞
            pass
        except Exception as e:
            warnings.append(f"底线检查异常: {e}")
            audit.log(quote_id, "floor_check_error", "sentinel",
                      notes=f"底线检查异常: {e}")
        
        # ── Step 4: 确定审核人 ──
        approver = "报价员"
        if total_amount > 200000:
            approver = "老板"
        elif total_amount > 50000:
            approver = "主管"
        
        # ── 汇编结果 ──
        audit_trail = audit.get_trace(quote_id)
        
        result = {
            "ok": True,
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
            "status": "pending_approval",
            # 新增字段
            "created_at": created_at,
            "revised_count": self._revised_count,
            "audit_trail_length": len(audit_trail),
        }
        
        # ── Step 5: 发布事件 ──
        try:
            await bus.publish(QUOTATION_COMPLETED, {
                "quotation_id": quote_id,
                "items": priced_items,
                "total": total_amount,
                "item_count": len(priced_items)
            })
        except Exception as e:
            # 事件发布失败不阻断结果返回
            result["event_publish_error"] = str(e)
        
        audit.log(quote_id, "completed", "quotation",
                  output_data={"total": total_amount, "approver": approver,
                               "revised_count": self._revised_count,
                               "audit_trail_length": len(audit_trail)})
        
        self._transition("waiting_human")
        self._last_result = result
        return result
    
    # ─── 审核操作 ───
    def approve(self) -> dict:
        """审核通过"""
        if self._status != "waiting_human":
            return {"ok": False, "step": "approve", "error": f"当前状态 {self._status} 不可通过审核"}
        self._transition("approved")
        quote_id = ""
        if self._last_result:
            self._last_result["status"] = "approved"
            quote_id = self._last_result.get("quotation_id", "")
        audit.log(quote_id, "approved", "quotation", decision="APPROVE")
        return {"ok": True, "status": "approved", "message": "审核已通过"}
    
    def reject(self, reason: str = "") -> dict:
        """审核驳回"""
        if self._status != "waiting_human":
            return {"ok": False, "step": "reject", "error": f"当前状态 {self._status} 不可驳回"}
        self._transition("rejected")
        quote_id = ""
        if self._last_result:
            self._last_result["status"] = "rejected"
            self._last_result["reject_reason"] = reason
            quote_id = self._last_result.get("quotation_id", "")
        audit.log(quote_id, "rejected", "quotation", decision="REJECT", notes=reason)
        return {"ok": True, "status": "rejected", "reason": reason, "message": "审核已驳回"}
    
    def revise(self, new_items: list, customer_id: str = None,
               trade_term: str = "FOB", payment_term: str = "prepaid") -> dict:
        """
        审核不通过后修改重新报价。
        状态: rejected → running (同步执行)
        返回: 结构化结果
        """
        if self._status != "rejected":
            return {"ok": False, "step": "revise",
                    "error": f"当前状态 {self._status} 不可修订，需先被驳回"}
        
        # 输入校验
        validation_error = self._validate_input(new_items)
        if validation_error:
            return validation_error
        
        # 标记修订
        self._revised_count += 1
        self._transition("running")
        
        # 复用 process 的核心逻辑（同步版本）
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 运行中的 loop，直接 await 可能在同步上下文，用新 loop
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    self.process(new_items, customer_id, trade_term, payment_term)
                )
                loop.close()
            else:
                result = loop.run_until_complete(
                    self.process(new_items, customer_id, trade_term, payment_term)
                )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.process(new_items, customer_id, trade_term, payment_term)
            )
            loop.close()
        
        result["revised_count"] = self._revised_count
        result["revision"] = True
        return result
    
    # ─── 报价对比 ───
    @staticmethod
    def compare_with_original(quote_result: dict, original_excel_path: str) -> dict:
        """
        对比报价结果与原始报价留底。
        
        Args:
            quote_result: process() 返回的报价结果 dict
            original_excel_path: 原始报价留底 Excel 文件路径
        
        Returns:
            {"ok": True, "matched": N, "diff_lines": [...], "accuracy_pct": 94.0,
             "missing_in_ours": [...], "missing_in_original": [...]}
        """
        if not Path(original_excel_path).exists():
            return {"ok": False, "step": "compare", "error": f"文件不存在: {original_excel_path}"}
        
        try:
            from atlas.parsers.enong_workbook import EnTongWorkbook
            wb = EnTongWorkbook(original_excel_path)
            original_parts = wb.parse_worksheet()
            original_quotation = wb.parse_quotation()
        except ImportError as e:
            return {"ok": False, "step": "compare", "error": f"无法导入解析器: {e}"}
        except ValueError as e:
            return {"ok": False, "step": "compare", "error": f"Sheet校验失败: {e}"}
        except Exception as e:
            return {"ok": False, "step": "compare", "error": f"解析Excel失败: {e}"}
        
        # 构建原始报价字典: {oe_number: {unit_price, total, name, ...}}
        original_map = {}
        for p in original_parts:
            oe = str(p.oe_number).strip()
            if oe and oe != 'None':
                original_map[oe] = {
                    "unit_price": p.discounted_price or p.list_price,
                    "total": p.discounted_total or p.list_price_total,
                    "name_cn": p.name_cn,
                    "brand": p.brand,
                    "pricing_mode": p.pricing_mode,
                }
        
        # 也纳入 quotation sheet 的行（以更高精度覆盖）
        for line in original_quotation.lines:
            oe = str(line.get("part_no", "")).strip()
            if oe and oe != 'None':
                original_map[oe] = {
                    "unit_price": line.get("unit_price", 0),
                    "total": line.get("total", 0),
                    "name_ru": line.get("name_ru", ""),
                }
        
        # 取出我方报价的 items
        our_items = quote_result.get("items", [])
        our_map = {}
        for item in our_items:
            oe = str(item.get("oe_number", "")).strip()
            if oe:
                our_map[oe] = item
        
        # 逐行对比
        all_oes = set(list(original_map.keys()) + list(our_map.keys()))
        matched = 0
        diff_lines = []
        missing_in_ours = []
        missing_in_original = []
        
        for oe in sorted(all_oes):
            orig = original_map.get(oe)
            ours = our_map.get(oe)
            
            if orig is None:
                missing_in_original.append({"oe": oe, "our_price": ours.get("unit_price", 0)})
                continue
            if ours is None:
                missing_in_ours.append({"oe": oe, "original_price": orig["unit_price"]})
                continue
            
            our_price = ours.get("unit_price", 0)
            original_price = orig["unit_price"]
            
            matched += 1
            
            # 差异超过1%视为不一致
            if original_price > 0:
                delta_pct = round((our_price - original_price) / original_price * 100, 2)
            elif our_price > 0:
                delta_pct = 100.0
            else:
                delta_pct = 0.0
            
            if abs(delta_pct) > 1.0:
                diff_lines.append({
                    "oe": oe,
                    "our_price": our_price,
                    "original_price": original_price,
                    "delta_pct": delta_pct,
                    "name_cn": ours.get("name_cn", ""),
                })
        
        # 计算准确率
        total_compared = matched + len(missing_in_ours) + len(missing_in_original)
        if total_compared == 0:
            accuracy_pct = 0.0
        else:
            accuracy_pct = round(matched / total_compared * 100, 2)
        
        return {
            "ok": True,
            "matched": matched,
            "diff_lines": diff_lines,
            "diff_count": len(diff_lines),
            "missing_in_ours": missing_in_ours,
            "missing_in_ours_count": len(missing_in_ours),
            "missing_in_original": missing_in_original,
            "missing_in_original_count": len(missing_in_original),
            "accuracy_pct": accuracy_pct,
        }
