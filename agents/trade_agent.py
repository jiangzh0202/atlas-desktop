"""
外贸智能体 (P2) — 完整实现
订阅询盘 → 翻译非中文内容 → 提取OE号/品名/数量 → 生成PI草稿
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bus.eventbus import bus, INQUIRY_RECEIVED
from oracle.client import translate, extract_inquiry, generate_pi
from ledger.trace import audit


class TradeAgent:
    """外贸智能体: 询盘翻译 + 信息提取 + PI生成"""

    def __init__(self):
        self.name = "trade"
        self.status = "idle"
        self.last_result = None  # 存储最近一次处理结果

    async def on_inquiry(self, event: dict):
        """
        处理收到的询盘事件:
        1. 检测语言，非中文则翻译
        2. 提取OE号、品名、数量
        3. 生成PI草稿
        4. 记录审计日志
        """
        self.status = "processing"
        payload = event.get("payload", {})
        inquiry_id = event.get("id", "unknown")
        original_text = payload.get("text", "")
        detected_lang = payload.get("language", "auto")
        customer_name = payload.get("customer", "")

        print(f"[TradeAgent] Received inquiry {inquiry_id}, lang={detected_lang}")

        result = {
            "inquiry_id": inquiry_id,
            "original_text": original_text,
            "detected_language": detected_lang,
            "translated_text": "",
            "extracted_items": [],
            "pi_draft": "",
            "needs_translation": False,
        }

        try:
            # Step 1: Translate if not Chinese
            if detected_lang != "zh" and original_text.strip():
                result["needs_translation"] = True
                print(f"[TradeAgent] Translating from {detected_lang} to zh...")
                translated = translate(original_text, target_lang="zh")
                result["translated_text"] = translated

                # Log translation step
                audit.log(
                    quotation_id=inquiry_id,
                    step="translate",
                    agent=self.name,
                    input_data={"text": original_text[:200], "lang": detected_lang},
                    output_data={"translated": translated[:200]},
                    notes=f"Translated {detected_lang} -> zh"
                )
            else:
                result["translated_text"] = original_text

            # Step 2: Extract structured items from translated text
            text_for_extraction = result["translated_text"] or original_text
            if text_for_extraction.strip():
                print(f"[TradeAgent] Extracting items...")
                extracted = extract_inquiry(text_for_extraction)
                result["extracted_items"] = extracted.get("items", [])
                result["customer_notes"] = extracted.get("customer_notes", "")

                # Log extraction step
                audit.log(
                    quotation_id=inquiry_id,
                    step="extract_items",
                    agent=self.name,
                    input_data={"text": text_for_extraction[:200]},
                    output_data={"items": result["extracted_items"]},
                    notes=f"Extracted {len(result['extracted_items'])} items"
                )

            # Step 3: Generate PI draft if items were found
            if result["extracted_items"]:
                print(f"[TradeAgent] Generating PI draft...")
                pi_draft = generate_pi(
                    inquiry_text=original_text,
                    items=result["extracted_items"],
                    customer_name=customer_name,
                    trade_term=payload.get("trade_term", "FOB"),
                    payment_term=payload.get("payment_term", "prepaid"),
                )
                result["pi_draft"] = pi_draft

                # Log PI generation step
                audit.log(
                    quotation_id=inquiry_id,
                    step="generate_pi",
                    agent=self.name,
                    input_data={"items_count": len(result["extracted_items"])},
                    output_data={"pi_draft": pi_draft[:500]},
                    notes="PI draft generated"
                )

            self.status = "idle"
            self.last_result = result
            print(f"[TradeAgent] Inquiry {inquiry_id} processed: "
                  f"translated={result['needs_translation']}, "
                  f"items={len(result['extracted_items'])}, "
                  f"pi={'generated' if result['pi_draft'] else 'skipped'}")

        except Exception as e:
            self.status = "error"
            print(f"[TradeAgent] Error processing inquiry {inquiry_id}: {e}")
            result["error"] = str(e)

        return result

    async def start(self):
        """Subscribe to inquiry events and start listening."""
        bus.subscribe(INQUIRY_RECEIVED, self.on_inquiry)
        self.status = "idle"
        print(f"[TradeAgent] Started, listening for inquiries")

    def get_last_result(self):
        """Return the last processing result (for API queries)."""
        return self.last_result


# Global singleton
trade_agent = TradeAgent()
