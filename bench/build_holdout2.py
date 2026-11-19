"""Second held-out set, written after the fixes that held-out set 1 exposed, and run exactly once for the README.
New sentence shapes: questions answered in one line, comparisons with "vs", numbers in parentheses, colon lists,
"X of Y" phrasing, causes and vehicles described in prose. Run: python bench/build_holdout2.py
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
rng = random.Random(23)
ttc = json.loads((HERE / "fixtures/ttc_tools.json").read_text())
gdp = json.loads((HERE / "fixtures/worldbank_gdp.json").read_text())["gdp_by_country"]
cases = []


def add(tools, before, target, after, label, form):
    cases.append({"id": len(cases), "tools": tools, "answer": before + target + after, "target": target,
                  "target_start": len(before), "label": label, "form": form, "category": "holdout2"})


def off(v, lo=0.15, hi=0.4):
    return v * (1 + rng.choice([-1, 1]) * rng.uniform(lo, hi))


rows = ttc["causes_for_route"]
tools = {"causes_for_route": rows}
named = [r for r in rows if r["events"] and r["lost_hours"]][:10]
for i, r in enumerate(named):
    c = r["cause_group"].replace("_", " ")
    other = named[(i + 2) % len(named)]
    add(tools, f"Why was 504 King late? Mostly {c}: ", f"{r['lost_hours']:g}", " hours lost.", "ok", "exact")
    add(tools, f"504 King ({c}): ", f"{r['events']:,}", f" events, {r['lost_hours']:g} hours.", "ok", "exact")
    add(tools, f"504 King ({c}): {r['events']:,} events, ", f"{r['lost_hours']:g}", " hours.", "ok", "exact")
    add(tools, f"504 King ({c}): ", f"{other['events']:,}", " events.", "bad", "swapped") \
        if abs(other["events"] - r["events"]) > 0.05 * r["events"] else None
    add(tools, f"Why was 504 King late? Mostly {c}: ", f"{off(r['lost_hours']):.1f}", " hours lost.", "bad", "fabricated")

rows = ttc["repeat_fault_vehicles"]
tools = {"repeat_fault_vehicles": rows}
for i, r in enumerate(rows):
    o = rows[(i + 1) % len(rows)]
    add(tools, f"Vehicle {r['vehicle_number']} vs {o['vehicle_number']}: ", str(r["equipment_faults"]),
        f" vs {o['equipment_faults']} equipment faults.", "ok", "exact")
    add(tools, f"Vehicle {r['vehicle_number']} vs {o['vehicle_number']}: {r['equipment_faults']} vs ",
        str(o["equipment_faults"]), " equipment faults.", "ok", "exact")
    add(tools, f"{r['repeat_faults']} of bus {r['vehicle_number']}'s ", str(r["equipment_faults"]),
        " equipment faults were repeats.", "ok", "exact")
    add(tools, "", str(r["repeat_faults"]), f" of bus {r['vehicle_number']}'s {r['equipment_faults']} equipment faults were repeats.",
        "ok", "exact")
    add(tools, f"Bus {r['vehicle_number']} repeated ", f"{round(r['repeat_faults'] / r['equipment_faults'] * 100)}%",
        " of its equipment faults.", "ok", "derived")
    add(tools, f"Bus {r['vehicle_number']} repeated ", f"{round(r['repeat_faults'] / r['equipment_faults'] * 100) - 12}%",
        " of its equipment faults.", "bad", "bad_math")
    add(tools, f"Vehicle {r['vehicle_number']} vs {o['vehicle_number']}: ", str(o["equipment_faults"] + 9),
        f" vs {o['equipment_faults']} equipment faults.", "bad", "fabricated")

by = {(r["country"], r["year"]): r["gdp_current_usd"] for r in gdp}
countries = sorted({r["country"] for r in gdp})
tools = {"gdp_by_country": gdp}
for i, c in enumerate(countries):
    o = countries[(i + 1) % len(countries)]
    a, b = by[(c, 2022)], by[(o, 2022)]
    add(tools, f"2022 GDP: {c} ", f"${a / 1e12:.2f}T", f" vs {o} ${b / 1e12:.2f}T.", "ok", "rounded")
    add(tools, f"2022 GDP: {c} ${a / 1e12:.2f}T vs {o} ", f"${b / 1e12:.2f}T", ".", "ok", "rounded")
    add(tools, f"2022 GDP: {c} ${a / 1e12:.2f}T vs {o} ", f"${a / 1e12:.2f}T", ".", "bad", "swapped") \
        if abs(a - b) > 0.05 * b else None
    add(tools, f"{c} added ", f"${(by[(c, 2023)] - by[(c, 2022)]) / 1e9:,.0f} billion", " of GDP between 2022 and 2023.",
        "ok", "derived") if by[(c, 2023)] > by[(c, 2022)] else None
    add(tools, f"2022 GDP: {c} ", f"${off(a) / 1e12:.2f}T", f" vs {o} ${b / 1e12:.2f}T.", "bad", "fabricated")

(HERE / "holdout2.jsonl").write_text("\n".join(json.dumps(c) for c in cases) + "\n")
from collections import Counter
print(len(cases), Counter((c["label"], c["form"]) for c in cases))
