import openpyxl, sys
from pathlib import Path

EXCEL = "/srv/atlas/tests/fixtures/dmitriy_quotation.xlsx"

def load_parts():
    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    ws = wb["报价留底"]
    parts = []
    for row in ws.iter_rows(min_row=4, max_row=171, values_only=True):
        if not row[2]: continue
        note = str(row[17]) if row[17] else ""
        if "库存一口价" in note or "一口价" in note: mode = "FIXED_STOCK"
        elif "含税进价" in note: mode = "COST_BASED"
        elif "一单一议" in note: mode = "NEGOTIATED"
        else: mode = "STANDARD"
        try: disc = float(row[13])
        except: disc = 0
        parts.append({
            "oe": str(row[2]).strip(), "name_ru": str(row[3])[:60],
            "qty": int(row[4] or 0), "brand": str(row[7] or "").strip(),
            "list_price": float(row[12] or 0), "discount_pct": disc,
            "discount_coeff": float(row[14] or 1),
            "final_price": float(row[15] or 0), "final_total": float(row[16] or 0),
            "note": note, "mode": mode
        })
    return parts

def match_discount(brand, price, qty):
    if "A2080" in brand or "ISF" in brand:
        if price <= 5: return (0, 1.0, "<=5,无折扣")
        elif price <= 50: return (16, 0.84, "5-50,15-17%")
        elif price <= 1000:
            if qty >= 30: return (24, 0.76, "50-1000,>=30,24%")
            return (23, 0.77, "50-1000,<30,23%")
        else:
            if qty >= 10: return (25.5, 0.745, ">1000,>=10,25.5%")
            return (24, 0.76, ">1000,<10,24%")
    elif "E9300" in brand:
        if price > 1000 and qty >= 30: return (17, 0.83, "E9300>1000>=30")
        return (15, 0.85, "E9300,15%")
    elif "卡友配" in brand:
        return (15, 0.85, "卡友配,15%")
    elif "东亚" in brand:
        return (7, 0.93, "东亚,7%")
    elif "BOSCH" in brand:
        return (24, 0.76, "BOSCH,24%")
    return (15, 0.85, "默认,15%")

def calculate(part):
    if part["mode"] == "FIXED_STOCK": return part["final_price"]
    if part["mode"] == "COST_BASED": return part["final_price"]
    if part["mode"] == "NEGOTIATED": return part["final_price"]
    _, coeff, _ = match_discount(part["brand"], part["list_price"], part["qty"])
    return round(part["list_price"] * coeff, 2)

# MAIN
parts = load_parts()
print(f"Loaded {len(parts)} parts from Dmitriy quotation")
modes = {}
for p in parts: modes[p["mode"]] = modes.get(p["mode"], 0) + 1
for m, c in sorted(modes.items(), key=lambda x: -x[1]):
    print(f"  {m}: {c} ({c/len(parts)*100:.1f}%)")

print("\nComparison (first 30 items):")
print(f"{OE:18} {Brand:12} {Orig:>10} {Calc:>10} {DevPct:>7} Mode")
print("-" * 75)
match = 0
for i, p in enumerate(parts[:30]):
    calc = calculate(p)
    orig = p["final_price"]
    dev = abs(calc - orig) / orig * 100 if orig > 0 else 0
    if dev < 2: match += 1
    s = "OK" if dev < 2 else ("~" if dev < 10 else "XX")
    print(f"{s} {p[oe][:16]:16} {p[brand][:10]:10} {orig:>10.2f} {calc:>10.2f} {dev:>6.1f}% {p[mode]}")

acc = match / 30 * 100
print(f"\nAccuracy: {acc:.0f}% (<2% deviation)")

# Total comparison
total_orig = sum(p["final_total"] for p in parts)
total_calc = sum(calculate(p) * p["qty"] for p in parts)
print(f"Total original: {total_orig:,.2f}")
print(f"Total calculated: {total_calc:,.2f}")
print(f"Deviation: {abs(total_calc-total_orig)/total_orig*100:.1f}%")
