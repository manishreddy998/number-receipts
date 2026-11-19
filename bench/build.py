"""Build labeled benchmark cases from real tool outputs.

Each case is one or two sentences an agent could write about the tool results, with one TARGET number whose truth
we know because we computed it from the data. Correct targets come in five forms (exact, rounded, hedged,
derived arithmetic, a count). Wrong targets come in six forms that agents actually produce:

  fabricated     a plausible number no tool returned
  swapped        another row's real value attached to this row (another route, another country)
  wrong_metric   a real value from the same row but a different field (27% within control vs 0.27% lost)
  transposed     digits swapped, 997.7 -> 979.7
  bad_math       arithmetic on the right rows done wrong (wrong base, wrong operand)
  wrong_scale    billion for trillion, thousand for million

The cases are generated from templates over real public data, not sampled from a live model, and the README says
so. Run: python bench/build.py  (writes bench/cases.jsonl, deterministic)
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
rng = random.Random(7)
ttc = json.loads((HERE / "fixtures/ttc_tools.json").read_text())
gdp = json.loads((HERE / "fixtures/worldbank_gdp.json").read_text())["gdp_by_country"]
cases = []


def num(v, dp=None):
    if dp is None:
        dp = 0 if float(v).is_integer() else 1
    return f"{v:,.{dp}f}"


def pct(v):
    return f"{v:g}%"


def add(tools, before, target, after, label, kind, category):
    answer = before + target + after
    cases.append({"id": len(cases), "tools": tools, "answer": answer, "target": target,
                  "target_start": len(before), "label": label, "form": kind, "category": category})


def far(v, others, rel=0.06):
    """A wrong value that is not within reach of any real value (so a fair checker can call it wrong)."""
    for _ in range(50):
        w = v * rng.choice([rng.uniform(0.55, 0.85), rng.uniform(1.15, 1.6)])
        if all(abs(w - o) > rel * max(abs(o), 1) for o in others):
            return w
    return v * 1.37


def transpose(v):
    s = f"{v:.1f}" if not float(v).is_integer() else str(int(v))
    digits = [i for i, ch in enumerate(s) if ch.isdigit()]
    for i in range(len(digits) - 1):
        a, b = digits[i], digits[i + 1]
        if s[a] != s[b] and b == a + 1:
            return float(s[:a] + s[b] + s[a] + s[b + 1:])
    return None


# ------------------------------------------------------------------ TTC routes (two tools: streetcar and bus)
for tool, mode in (("lost_time_by_route", "streetcar"), ("lost_time_by_route_bus", "bus")):
    rows = ttc[tool]
    tools = {tool: rows}
    name = lambda r: f"{r['route']} {r['name']}"
    hours = [r["lost_hours"] for r in rows]
    for i, r in enumerate(rows):
        others = [x for x in rows if x is not r]
        b = others[0]
        h = r["lost_hours"]
        pre = f"The {name(r)} {mode} route lost "
        add(tools, pre, num(h), " hours.", "ok", "exact", "ttc")
        add(tools, pre, f"{round(h):,}", " hours.", "ok", "rounded", "ttc")
        add(tools, pre + "about ", f"{round(h, -1):,.0f}", " hours.", "ok", "hedged", "ttc")
        add(tools, f"The {name(r)} {mode} route lost ", pct(r["pct_of_planned_lost"]), " of its planned hours.", "ok", "exact", "ttc")
        add(tools, f"{name(r)}: ", pct(r["pct_within_ttc_control"]), " of its lost time was within the TTC's control.",
            "ok", "exact", "ttc")
        diff = h - b["lost_hours"]
        if diff > 0:
            add(tools, f"The {name(r)} lost ", num(round(diff, 1)), f" more hours than {name(b)}.", "ok", "derived", "ttc")
        share = h / sum(hours) * 100
        add(tools, f"Across these {mode} routes, {name(r)} accounted for ", pct(round(share, 1)), " of the lost hours.",
            "ok", "derived", "ttc")
        add(tools, f"Together the listed {mode} routes lost ", f"{round(sum(hours)):,}", " hours.", "ok", "derived", "ttc")
        add(tools, f"The list covers ", str(len(rows)), f" {mode} routes.", "ok", "count", "ttc")
        # wrong
        add(tools, pre, num(round(far(h, hours), 1)), " hours.", "bad", "fabricated", "ttc")
        if abs(b["lost_hours"] - h) > 0.03 * h:
            add(tools, pre, num(b["lost_hours"]), " hours.", "bad", "swapped", "ttc")
        if abs(r["pct_within_ttc_control"] - r["pct_of_planned_lost"]) > 0.5:
            add(tools, f"The {name(r)} {mode} route lost ", pct(r["pct_within_ttc_control"]), " of its planned hours.",
                "bad", "wrong_metric", "ttc")
        t = transpose(h)
        if t and abs(t - h) > 1:
            add(tools, pre, num(t), " hours.", "bad", "transposed", "ttc")
        if diff > 0:
            wrong = diff / b["lost_hours"] * 100        # percent quoted as if it were hours
            add(tools, f"The {name(r)} lost ", num(round(h - others[-1]["lost_hours"] + 25, 1)), f" more hours than {name(b)}.",
                "bad", "bad_math", "ttc")
        add(tools, f"Across these {mode} routes, {name(r)} accounted for ", pct(round(h / sum(hours[:2]) * 100 + 7, 1)),
            " of the lost hours.", "bad", "bad_math", "ttc")

# ------------------------------------------------------------------ TTC vehicles with repeat faults
rows = ttc["repeat_fault_vehicles"]
tools = {"repeat_fault_vehicles": rows}
for r in rows:
    others = [x for x in rows if x is not r]
    v = f"Bus {r['vehicle_number']}"
    add(tools, f"{v} had ", str(r["equipment_faults"]), " equipment faults.", "ok", "exact", "ttc")
    add(tools, f"{v} had ", str(r["repeat_faults"]), " repeat faults within 30 days of the previous one.", "ok", "exact", "ttc")
    add(tools, f"{v} served ", str(r["routes_served"]), " routes.", "ok", "exact", "ttc")
    add(tools, f"{v} lost ", num(r["equipment_hours"]), " hours to equipment faults.", "ok", "exact", "ttc")
    add(tools, f"{v} had ", str(round(far(r["equipment_faults"], [x["equipment_faults"] for x in rows]))), " equipment faults.",
        "bad", "fabricated", "ttc")
    sw = next((x for x in others if abs(x["equipment_faults"] - r["equipment_faults"]) >= 3), None)
    if sw:
        add(tools, f"{v} had ", str(sw["equipment_faults"]), " equipment faults.", "bad", "swapped", "ttc")
    add(tools, f"{v} served ", str(r["repeat_faults"]), " routes.", "bad", "wrong_metric", "ttc")

# ------------------------------------------------------------------ TTC causes on route 504
rows = ttc["causes_for_route"]
tools = {"causes_for_route": rows}
for r in rows[:8]:
    c = r["cause_group"].replace("_", " ")
    add(tools, f"On route 504, {c} caused ", f"{r['events']:,}", " delay events.", "ok", "exact", "ttc")
    add(tools, f"On route 504, {c} cost ", num(r["lost_hours"]), " lost hours.", "ok", "exact", "ttc")
    add(tools, f"On route 504, {c} caused ", f"{round(far(r['events'], [x['events'] for x in rows])):,}", " delay events.",
        "bad", "fabricated", "ttc")
    sw = next((x for x in rows if x is not r and abs(x["lost_hours"] - r["lost_hours"]) > 0.05 * r["lost_hours"]), None)
    add(tools, f"On route 504, {c} cost ", num(sw["lost_hours"]), " lost hours.", "bad", "swapped", "ttc")

# ------------------------------------------------------------------ World Bank GDP
by = {(r["country"], r["year"]): r["gdp_current_usd"] for r in gdp}
countries = sorted({r["country"] for r in gdp})
tools = {"gdp_by_country": gdp}
alias = {"United States": "the United States", "United Kingdom": "the United Kingdom"}
T = 1e12
for c in countries:
    n = alias.get(c, c)
    g23, g22, g21 = by[(c, 2023)], by[(c, 2022)], by[(c, 2021)]
    allv = list(by.values())
    tr = lambda v, dp=2: f"${v / T:.{dp}f} trillion"
    add(tools, f"In 2023, {n} had a GDP of ", tr(g23), ".", "ok", "rounded", "gdp")
    add(tools, f"{n}'s GDP was about ", tr(g23, 1), " in 2023.", "ok", "hedged", "gdp")
    ch = (g23 - g22) / g22 * 100
    add(tools, f"{n}'s GDP changed by ", pct(round(ch, 1)), " from 2022 to 2023.", "ok", "derived", "gdp")
    other = countries[(countries.index(c) + 3) % len(countries)]
    ratio = g23 / by[(other, 2023)]
    if ratio >= 1:
        add(tools, f"In 2023 {n}'s GDP was ", f"{ratio:.1f}x", f" that of {alias.get(other, other)}.", "ok", "derived", "gdp")
    # wrong
    add(tools, f"In 2023, {n} had a GDP of ", tr(far(g23, allv, 0.03)), ".", "bad", "fabricated", "gdp")
    sw = next(by[(o, 2023)] for o in countries if o != c and abs(by[(o, 2023)] - g23) > 0.05 * g23)
    add(tools, f"In 2023, {n} had a GDP of ", tr(sw), ".", "bad", "swapped", "gdp")
    add(tools, f"In 2023, {n} had a GDP of ", tr(g21), ".", "bad", "swapped", "gdp") if abs(g21 - g23) > 0.05 * g23 else None
    add(tools, f"In 2023, {n} had a GDP of ", f"${g23 / 1e9:.2f} billion".replace(f"{g23 / 1e9:.2f}", f"{g23 / T:.2f}"), ".",
        "bad", "wrong_scale", "gdp")
    wrong_change = (g23 - g22) / g23 * 100           # wrong base
    if abs(wrong_change - ch) > 0.3:
        add(tools, f"{n}'s GDP changed by ", pct(round(wrong_change + (1.5 if abs(wrong_change - ch) < 1 else 0), 1)),
            " from 2022 to 2023.", "bad", "bad_math", "gdp")

out = HERE / "cases.jsonl"
out.write_text("\n".join(json.dumps(c) for c in cases) + "\n")
from collections import Counter
print(len(cases), "cases", Counter((c["label"], c["form"]) for c in cases))
