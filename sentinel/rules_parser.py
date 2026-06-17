"""
擎天·规则解析器 — Markdown 大白话 → JSON 结构化规则
借鉴 KWeaver BKN Lang：老板写 Markdown，系统解析执行
"""
import re, json
from pathlib import Path

def parse_rules_md(md_path: str) -> dict:
    """解析 Markdown 规则文件为 JSON"""
    text = Path(md_path).read_text(encoding="utf-8")
    
    rules = {
        "customer_tiers": {},
        "brand_matrices": {},
        "approval_rules": [],
        "price_floors": [],
        "temp_policies": [],
        "raw": text
    }
    
    # 解析客户分级
    for m in re.finditer(r'[-*]\s*(\S+)客户[：:]\s*(.+)', text):
        tier_name = m.group(1).replace("星", "").strip()
        desc = m.group(2).strip()
        try:
            tier = int(tier_name)
            rules["customer_tiers"][str(tier)] = desc
        except: pass
    
    # 解析品牌折扣矩阵
    current_brand = None
    for line in text.split("\n"):
        brand_match = re.match(r'###\s+(.+)', line)
        if brand_match:
            current_brand = brand_match.group(1).strip()
            if current_brand not in rules["brand_matrices"]:
                rules["brand_matrices"][current_brand] = []
            continue
        
        range_match = re.match(r'-\s*(.+?)[：:]\s*(.+)', line)
        if range_match and current_brand:
            rules["brand_matrices"][current_brand].append({
                "range": range_match.group(1).strip(),
                "rule": range_match.group(2).strip()
            })
    
    # 解析审核规则
    for m in re.finditer(r'总额[＜<](\d+)万.*→\s*(.+)', text):
        rules["approval_rules"].append({
            "threshold": int(m.group(1)) * 10000,
            "approver": m.group(2).strip()
        })
    
    # 解析价格底线
    for m in re.finditer(r'不得低于(.+)', text):
        rules["price_floors"].append(m.group(1).strip())
    
    return rules

def load_rules(rules_path: str = None) -> dict:
    """加载规则（优先 JSON，fallback 到 Markdown）"""
    if rules_path is None:
        rules_path = "/srv/atlas/data/rules.md"
    
    p = Path(rules_path)
    if not p.exists():
        return {"error": f"Rules file not found: {rules_path}"}
    
    if p.suffix == '.md':
        return parse_rules_md(str(p))
    elif p.suffix == '.json':
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

# 测试
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/srv/atlas/data/rules.md"
    rules = parse_rules_md(path)
    print(json.dumps(rules, ensure_ascii=False, indent=2))
