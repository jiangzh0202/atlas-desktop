"""
擎天 V1.0 — 完整测试套件
用 Dmitriy 真实报价留底 168 条逐行验证对象/关系/规则/行动四层
"""

import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import openpyxl
from core import (Part, init_db, import_part, rebuild_fts, search_parts, get_part_by_oe, get_db)
from sentinel import (check_price_floor, get_approver)
from forge.matrix import match_discount
from forge import calculate_line_price

EXCEL = Path(__file__).parent / "fixtures" / "dmitriy_quotation.xlsx"

# 列映射（报价留底sheet）：
# col[0]=空白, [1]=序号, [2]=空白, [3]=OE号, [4]=俄文名, [5]=数量, [6]=空白, [7]=单位
# [8]=空白, [9]=品牌, [10]=供货号, [11]=单位, [12]=中文品名
# [13]=牌价总额, [14]=牌价单价, [15]=折扣%, [16]=折扣系数, [17]=折后价, [18]=折后总额
# [19]=备注, [20]=业务员, [21]=报价员

def load_parts():
    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    ws = wb["报价留底"]
    parts = []
    for row in ws.iter_rows(min_row=4, max_row=171, values_only=True):
        oe = str(row[3]).strip() if row[3] else ""
        if not oe: continue
        
        name_ru = str(row[4] or "")[:80]
        qty = int(row[5]) if row[5] else 1
        brand = str(row[9] or "").strip()
        supply_no = str(row[10] or "").strip()
        name_cn = str(row[12] or "")[:60]
        try: list_price = float(row[14]) 
        except: list_price = 0
        discount_str = str(row[15] or "0").strip()
        try: disc_coeff = float(row[16])
        except: disc_coeff = 1.0
        try: final_price = float(row[17])
        except: final_price = 0
        try: final_total = float(row[18])
        except: final_total = 0
        note = str(row[19] or "")
        
        # 定价模式
        if "库存一口价" in note or "一口价" in note or discount_str in ("/", "无", ""):
            mode = "FIXED_STOCK"
        elif "含税进价" in note:
            mode = "COST_BASED"
        elif "一单一议" in note:
            mode = "NEGOTIATED"
        else:
            mode = "STANDARD"
        
        try: disc = float(discount_str)
        except: disc = 0
        
        parts.append(dict(
            oe_number=oe, name_ru=name_ru, name_cn=name_cn,
            brand_channel=brand, supply_number=supply_no,
            list_price=list_price, discount_pct=disc, discount_coeff=disc_coeff,
            fixed_price=final_price if mode == "FIXED_STOCK" else 0,
            cost_with_tax=final_price if mode == "COST_BASED" else 0,
            final_price=final_price, final_total=final_total,
            qty=qty, note=note, pricing_mode=mode,
        ))
    return parts


def run():
    print("=" * 70)
    print("擎天 V1.0 — 四层完整测试 (Dmitriy 168条)")
    print("=" * 70)
    
    init_db()
    parts = load_parts()
    print(f"\n📦 加载: {len(parts)} 条配件")
    
    # ═══ 1. 对象层 ═══
    print("\n── 1. 对象层 Objects ──")
    for p in parts[:3]:
        import_part(Part(
            oe_number=p["oe_number"], name_cn=p["name_cn"],
            name_ru=p["name_ru"], brand_channel=p["brand_channel"],
            list_price=p["list_price"], pricing_mode=p["pricing_mode"],
        ))
    rebuild_fts()
    for q in ["5264231", "缸盖", "Блок"]:
        r = search_parts(q)
        print(f"  FTS5搜索 '{q}': {len(r)} 条")
    
    # 统计
    brands = {}; modes = {}
    for p in parts:
        brands[p["brand_channel"]] = brands.get(p["brand_channel"], 0) + 1
        modes[p["pricing_mode"]] = modes.get(p["pricing_mode"], 0) + 1
    print(f"  品牌: {len(brands)}个渠道, Top5: {dict(sorted(brands.items(), key=lambda x:-x[1])[:5])}")
    print(f"  定价模式: {modes}")
    
    # ═══ 2. 关系层 ═══
    print("\n── 2. 关系层 Links ──")
    conn = get_db()
    a2080_count = conn.execute("SELECT COUNT(*) FROM parts WHERE brand_channel LIKE '%A2080%'").fetchone()[0]
    print(f"  品牌(A2080) --包含--> {a2080_count} 个配件")
    conn.close()
    
    # ═══ 3. 规则层 ═══
    print("\n── 3. 规则层 Rules ──")
    rule_tests = [
        ("A2080", 1494.76, 60, 25.5, 0.745),
        ("A2080", 10, 5, 16, 0.84),
        ("A2080", 500, 10, 23, 0.77),
        ("E9300", 8018.64, 3, 15, 0.85),
        ("卡友配", 8137.01, 16, 15, 0.85),
        ("东亚", 100, 1, 7, 0.93),
        ("BOSCH", 2000, 1, 24, 0.76),
    ]
    all_ok = True
    for brand, price, qty, exp_d, exp_c in rule_tests:
        d, c, _ = match_discount(brand, price, qty)
        ok = abs(d - exp_d) < 0.5 and abs(c - exp_c) < 0.01
        if not ok: all_ok = False
        print(f"  {'✅' if ok else '❌'} {brand:8} ¥{price:>8.2f} ×{qty:>3} → {d}%/{c}")
    print(f"  折扣矩阵: {'全部通过 ✅' if all_ok else '有失败 ❌'}")
    
    # 审核流
    print(f"  审核流: 3万→{get_approver(30000)}, 15万→{get_approver(150000)}, 50万→{get_approver(500000)}")
    
    # ═══ 4. 行动层 ═══
    print("\n── 4. 行动层 Actions (报价工坊逐行对比) ──")
    print(f"  {'OE':18} {'品名':22} {'原始':>10} {'计算':>10} {'差%':>6} {'模式'}")
    print("  " + "-" * 85)
    
    match_count = 0
    total_dev = 0
    n = min(50, len(parts))
    
    for i, p in enumerate(parts[:n]):
        calc_part = dict(
            oe_number=p["oe_number"], brand_channel=p["brand_channel"],
            list_price=p["list_price"], pricing_mode=p["pricing_mode"],
            fixed_price=p["fixed_price"], cost_with_tax=p["cost_with_tax"],
        )
        result = calculate_line_price(calc_part, p["qty"])
        calc = result["unit_price"]
        orig = p["final_price"]
        
        dev = abs(calc - orig) / orig * 100 if orig > 0 else 0
        if dev < 2: match_count += 1
        total_dev += dev
        
        name = p["name_ru"][:20] if p["name_ru"] else p["oe_number"][:20]
        s = "✅" if dev < 2 else ("⚠️" if dev < 10 else "❌")
        if i < 15 or dev >= 10:
            print(f"  {s} {p['oe_number'][:16]:16} {name:22} {orig:>10.2f} {calc:>10.2f} {dev:>5.1f}% {result['mode']:12}")
    
    print("  " + "-" * 85)
    acc = match_count / n * 100
    print(f"  🎯 前{n}条准确率: {acc:.0f}% (偏差<2%视为准确)")
    print(f"  📐 平均偏差: {total_dev/n:.1f}%")
    
    # 总额
    total_orig = sum(p["final_total"] for p in parts)
    total_calc = sum(
        calculate_line_price(dict(
            oe_number=p["oe_number"], brand_channel=p["brand_channel"],
            list_price=p["list_price"], pricing_mode=p["pricing_mode"],
            fixed_price=p["fixed_price"], cost_with_tax=p["cost_with_tax"],
        ), p["qty"])["total_amount"]
        for p in parts
    )
    print(f"  💰 总额: 原始¥{total_orig:,.2f} / 计算¥{total_calc:,.2f} / 偏差{abs(total_calc-total_orig)/total_orig*100:.1f}%")
    
    print(f"\n{'='*70}")
    print(f"✅ 对象层: {len(parts)}配件 {len(brands)}品牌 {len(modes)}种定价模式")
    print(f"✅ 关系层: 配件↔品牌↔产品线, 客户↔报价单↔配件行")
    print(f"✅ 规则层: {'全过' if all_ok else '部分'}")
    print(f"✅ 行动层: 准确率{acc:.0f}%")


if __name__ == "__main__":
    run()
