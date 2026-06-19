"""
报价员 · 审查标准（受保护核心IP）
────────────────────────────────
这是软件最核心的审查规则，是刚性结构。
任何改动必须：
  ✓ 只能新增字段或规则
  ✓ 不能删除已有规则
  ✓ 不能修改已有规则的阈值（除非用户明确授权）
  ✓ 每次修改写入审计日志

结构:
  sentinel/rules.json — 原始 JSON（由 rules.md 生成）
  sentinel/audit.log  — 所有改动记录
"""
import json, os, hashlib, datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


# ═══════════════════════════════════════════════
# 不可变字段列表 — 这些字段一旦存在就不能删
# ═══════════════════════════════════════════════
IMMUTABLE_FIELDS = [
    "version",
    "description",
    "source",
    "customer_tiers",       # 七星客户标准
    "brand_matrices",       # 品牌折扣矩阵
    "brands",               # 品牌详细规则
    "approval_flow",        # 审批流程
    "price_floors",         # 价格底线
    "temporary_policies",   # 临时政策
]

PROTECTED_BRANDS = [
    "A2080",     # ISF 系列散件
    "卡友配",
    "E9300",
    "东亚",
    "BOSCH",
]

PROTECTED_CUSTOMER_TIERS = [1, 2, 3, 4, 5, 6, 7]


class ReviewCriteria:
    """
    报价审查标准 — 受保护的数据对象
    
    使用方式：
        criteria = ReviewCriteria.load()
        
        # 只允许新增，JSON Schema 保证结构
        criteria.add_brand_rule("新品牌", [...])
        criteria.add_customer_tier(8, "自定义规则")
        
        # 删除会抛异常
        criteria.remove_brand("A2080")  # → ImmutableRuleError
    """
    
    def __init__(self, data: dict, filepath: str = ""):
        self._data = data
        self._filepath = filepath
        self._original_hash = self._compute_hash()
    
    # ───── 加载 / 保存 ─────
    @classmethod
    def load(cls, filepath: str = None) -> "ReviewCriteria":
        """从 rules.json 加载审查标准"""
        if filepath is None:
            filepath = Path(__file__).parent / "sentinel" / "rules.json"
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 校验完整性
        cls._validate_structure(data)
        
        return cls(data, str(filepath))
    
    def save(self):
        """保存到文件（含审计日志）"""
        if not self._filepath:
            raise ValueError("无法保存：未设置文件路径")
        
        new_hash = self._compute_hash()
        if new_hash == self._original_hash:
            return  # 无变化
        
        # 写审计日志
        self._write_audit(self._original_hash, new_hash)
        
        # 写入文件
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        
        self._original_hash = new_hash
    
    # ───── 只读查询 ─────
    @property
    def customer_tiers(self) -> dict:
        return self._data.get("customer_tiers", {})
    
    @property
    def brands(self) -> dict:
        return self._data.get("brands", {})
    
    @property
    def brand_matrices(self) -> dict:
        return self._data.get("brand_matrices", {})
    
    @property
    def approval_flow(self) -> list:
        return self._data.get("approval_flow", [])
    
    @property
    def price_floors(self) -> list:
        return self._data.get("price_floors", [])
    
    @property
    def temporary_policies(self) -> list:
        return self._data.get("temporary_policies", [])
    
    @property
    def version(self) -> str:
        return self._data.get("version", "0")
    
    @property
    def all_data(self) -> dict:
        """返回完整数据的深拷贝（外部不能修改原件）"""
        return json.loads(json.dumps(self._data))
    
    # ───── 只允许新增的操作 ─────
    def add_brand_rule(self, brand_code: str, tiers: List[dict],
                        cap_discount: float = 0,
                        special_policy: str = "",
                        min_order_amount: int = None) -> "ReviewCriteria":
        """新增品牌规则（只能新增，不能修改已有品牌）"""
        if brand_code in self._data.get("brands", {}):
            raise ImmutableRuleError(
                f"品牌 '{brand_code}' 已存在。不能修改已有品牌，只能新增。"
            )
        
        brand_entry = {
            "tiers": tiers,
            "cap_discount": cap_discount
        }
        if special_policy:
            brand_entry["special_policy"] = special_policy
        if min_order_amount:
            brand_entry["min_order_amount"] = min_order_amount
        
        self._data.setdefault("brands", {})[brand_code] = brand_entry
        return self
    
    def add_customer_tier(self, tier: int, rule: str) -> "ReviewCriteria":
        """新增客户等级（只能新增，已有等级不能改）"""
        if str(tier) in self._data.get("customer_tiers", {}):
            raise ImmutableRuleError(
                f"客户等级 {tier} 已存在。不能修改已有等级，只能新增。"
            )
        
        self._data.setdefault("customer_tiers", {})[str(tier)] = rule
        return self
    
    def add_price_floor(self, floor_id: str, description: str) -> "ReviewCriteria":
        """新增价格底线"""
        floors = self._data.setdefault("price_floors", [])
        if any(f.get("id") == floor_id for f in floors):
            raise ImmutableRuleError(f"价格底线 '{floor_id}' 已存在。")
        
        floors.append({"id": floor_id, "desc": description})
        return self
    
    def add_temporary_policy(self, policy: str) -> "ReviewCriteria":
        """新增临时政策"""
        policies = self._data.setdefault("temporary_policies", [])
        if policy in policies:
            raise ImmutableRuleError("该临时政策已存在。")
        
        policies.append(policy)
        return self
    
    def add_approval_step(self, amount: int, approver: str) -> "ReviewCriteria":
        """新增审批层级"""
        flow = self._data.setdefault("approval_flow", [])
        flow.append({"amount": amount, "approver": approver})
        # 按金额排序
        flow.sort(key=lambda x: x["amount"])
        return self
    
    # ───── 禁止的操作（会抛异常）─────
    def remove_brand(self, brand_code: str):
        """禁止删除品牌"""
        raise ImmutableRuleError(
            f"禁止删除品牌 '{brand_code}'。审查标准只能丰富，不能减少。"
        )
    
    def remove_customer_tier(self, tier: int):
        """禁止删除客户等级"""
        raise ImmutableRuleError(
            f"禁止删除客户等级 {tier}。审查标准只能丰富，不能减少。"
        )
    
    def remove_any(self, path: str):
        """禁止删除任何已存在字段"""
        raise ImmutableRuleError(
            f"禁止删除 '{path}'。审查标准只能丰富，不能减少。"
        )
    
    # ───── 完整性校验 ─────
    @staticmethod
    def _validate_structure(data: dict):
        """校验审查表结构完整性"""
        errors = []
        
        for field in IMMUTABLE_FIELDS:
            if field not in data:
                errors.append(f"缺少核心字段: {field}")
        
        for brand in PROTECTED_BRANDS:
            if brand not in data.get("brands", {}):
                errors.append(f"缺少受保护品牌: {brand}")
        
        for tier in PROTECTED_CUSTOMER_TIERS:
            if str(tier) not in data.get("customer_tiers", {}):
                errors.append(f"缺少七星等级: {tier}")
        
        if errors:
            raise CriteriaValidationError(
                "审查标准完整性校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
            )
    
    # ───── 审计 ─────
    def _compute_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self._data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
    
    def _write_audit(self, old_hash: str, new_hash: str):
        audit_path = Path(self._filepath).parent / "audit.log"
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "old_hash": old_hash,
            "new_hash": new_hash,
            "version_before": self._data.get("version", "?"),
        }
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ═══════════════════════════════════════════════
# 自定义异常
# ═══════════════════════════════════════════════
class ImmutableRuleError(Exception):
    """审查规则不可变性违反"""
    pass


class CriteriaValidationError(Exception):
    """审查标准校验失败"""
    pass


# ═══════════════════════════════════════════════
# CLI 工具
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python review_criteria.py <command>")
        print("  validate  - 校验审查表完整性")
        print("  audit     - 查看审计日志")
        print("  version   - 显示当前版本")
        sys.exit(0)
    
    cmd = sys.argv[1]
    criteria = ReviewCriteria.load()
    
    if cmd == "validate":
        print(f"✅ 审查标准 v{criteria.version} 完整性校验通过")
        print(f"   品牌: {list(criteria.brands.keys())}")
        print(f"   客户等级: {list(criteria.customer_tiers.keys())}")
        print(f"   价格底线: {len(criteria.price_floors)} 条")
        print(f"   审批层级: {len(criteria.approval_flow)} 层")
    
    elif cmd == "audit":
        audit_path = Path(__file__).parent / "sentinel" / "audit.log"
        if audit_path.exists():
            print(open(audit_path).read())
        else:
            print("暂无审计记录")
    
    elif cmd == "version":
        print(f"v{criteria.version}")
