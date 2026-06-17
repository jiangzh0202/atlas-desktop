"""
擎天·审计日志 — 借鉴 KWeaver TraceAI
每笔报价计算链可追溯
"""
import json, os, uuid, time
from pathlib import Path

AUDIT_DIR = os.environ.get("ATLAS_AUDIT_DIR", "/srv/atlas/data/audit")

class AuditLog:
    """记录每一步操作，支持完整追溯链"""
    
    def __init__(self, audit_dir: str = None):
        self.dir = Path(audit_dir or AUDIT_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
    
    def _log_file(self, quotation_id: str):
        return self.dir / f"quote_{quotation_id}.jsonl"
    
    def log(self, quotation_id: str, step: str, agent: str, 
            input_data: dict = None, output_data: dict = None, 
            decision: str = "", notes: str = ""):
        entry = {
            "id": uuid.uuid4().hex[:8],
            "quotation_id": quotation_id,
            "step": step,
            "agent": agent,
            "timestamp": time.time(),
            "input": input_data or {},
            "output": output_data or {},
            "decision": decision,
            "notes": notes
        }
        with open(self._log_file(quotation_id), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    def get_trace(self, quotation_id: str) -> list:
        """返回完整追溯链"""
        f = self._log_file(quotation_id)
        if not f.exists(): return []
        trace = []
        with open(f) as fh:
            for line in fh:
                try: trace.append(json.loads(line.strip()))
                except: pass
        return trace
    
    def get_all_quotes(self) -> list:
        """列出所有报价ID"""
        ids = []
        for f in sorted(self.dir.glob("quote_*.jsonl"), reverse=True):
            ids.append(f.stem.replace("quote_", ""))
        return ids

# 全局实例
audit = AuditLog()
