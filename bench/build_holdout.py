"""Held-out cases, written after the checker was tuned on cases.jsonl and run once. Different phrasing (passive
voice, bullet lists, several numbers per sentence, numbers before the name), tools the dev set never used
(data_quality, vehicle_history) and the bus routes table. Run: python bench/build_holdout.py
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
rng = random.Random(11)
ttc = json.loads((HERE / "fixtures/ttc_tools.json").read_text())
gdp = json.loads((HERE / "fixtures/worldbank_gdp.json").read_text())["gdp_by_country"]
cases = []


def add(tools, before, target, after, label, form, category):
    cases.append({"id": len(cases), "tools": tools, "answer": before + target + after, "target": target,
                  "target_start": len(before), "label": label, "form": form, "category": category})


def off(v, lo=0.2, hi=0.45):
    return v * (1 + rng.choice([-1, 1]) * rng.uniform(lo, hi))


# data quality checks: counts and percents of events
dq = [r for r in ttc["data_quality"] if r.get("pct_of_events") is not None and r.get("events")]
tools = {"data_quality": dq}
for r in dq:
    n = r["check_name"]
    add(tools, f"- {n}: ", f"{r['events']:,}", f" events ({r['pct_of_events']}% of all events)", "ok", "exact", "holdout")
    add(tools, f"- {n}: {r['events']:,} events (", f"{r['pct_of_events']}%", " of all events)", "ok", "exact", "holdout")
    add(tools, f"The check for {n} matched roughly ", f"{round(r['events'], -2):,.0f}", " events.", "ok", "hedged", "holdout")
    add(tools, f"- {n}: ", f"{round(off(r['events'])):,}", " events", "bad", "fabricated", "holdout")
    other = next(x for x in dq if x is not r and abs(x["pct_of_events"] - r["pct_of_events"]) > 0.3)
    add(tools, f"- {n}: {r['events']:,} events (", f"{other['pct_of_events']}%", " of all events)", "bad", "swapped", "holdout")

# one vehicle's history: summary plus recent events
vh = ttc["vehicle_history"]
s = vh["summary"][0]
tools = {"vehicle_history": vh}
add(tools, f"Over {s['first_seen']} to {s['last_seen']}, bus {s['vehicle_number']} logged ", str(s["delay_events"]),
    " delays.", "ok", "exact", "holdout")
add(tools, f"Bus {s['vehicle_number']} lost ", f"{s['lost_minutes']:,}", " minutes in total, of which "
    f"{s['equipment_minutes']} were equipment faults.", "ok", "exact", "holdout")
add(tools, f"Bus {s['vehicle_number']} lost {s['lost_minutes']:,} minutes in total, of which ", str(s["equipment_minutes"]),
    " were equipment faults.", "ok", "exact", "holdout")
add(tools, f"Equipment faults made up ", f"{round(s['equipment_minutes'] / s['lost_minutes'] * 100)}%",
    f" of the {s['lost_minutes']:,} minutes bus {s['vehicle_number']} lost.", "ok", "derived", "holdout")
add(tools, f"Bus {s['vehicle_number']} lost ", f"{round(off(s['lost_minutes'])):,}", " minutes in total.", "bad",
    "fabricated", "holdout")
add(tools, f"Bus {s['vehicle_number']} logged ", str(s["equipment_faults"]), " delays in total.", "bad", "wrong_metric",
    "holdout")
for e in vh["recent_events"][:6]:
    add(tools, f"On {e['event_date']} the bus was held for ", str(e["delay_minutes"]), f" minutes ({(e['code_description'] or 'no code').lower()}).",
        "ok", "exact", "holdout")

# bus routes, written the other way round and with several numbers per sentence
rows = ttc["lost_time_by_route_bus"]
tools = {"lost_time_by_route_bus": rows}
for i, r in enumerate(rows):
    nm = f"{r['route']} {r['name']}"
    nxt = rows[(i + 1) % len(rows)]
    add(tools, "", f"{r['lost_hours']:,}", f" hours were lost on {nm}, {r['pct_within_ttc_control']:g}% of them within TTC control.",
        "ok", "exact", "holdout")
    add(tools, f"{r['lost_hours']:,} hours were lost on {nm}, ", f"{r['pct_within_ttc_control']:g}%",
        " of them within TTC control.", "ok", "exact", "holdout")
    add(tools, f"{nm} lost {round(r['lost_hours']):,} hours and {nxt['route']} {nxt['name']} lost ",
        f"{round(nxt['lost_hours']):,}", ".", "ok", "rounded", "holdout")
    add(tools, f"{nm} lost {round(r['lost_hours']):,} hours and {nxt['route']} {nxt['name']} lost ",
        f"{round(r['lost_hours']):,}", ".", "bad", "swapped", "holdout") if abs(r["lost_hours"] - nxt["lost_hours"]) > 5 else None
    add(tools, f"Of {nm}'s planned hours, ", f"{r['pct_within_ttc_control']:g}%", " were lost.", "bad", "wrong_metric", "holdout")
    add(tools, f"{nm} lost ", f"{round(off(r['lost_hours'], 0.08, 0.2)):,}", " hours.", "bad", "fabricated", "holdout")

# GDP across years, in prose a model might write
by = {(r["country"], r["year"]): r["gdp_current_usd"] for r in gdp}
tools = {"gdp_by_country": gdp}
for c in sorted({r["country"] for r in gdp}):
    g21, g23 = by[(c, 2021)], by[(c, 2023)]
    add(tools, f"Between 2021 and 2023, {c}'s economy grew from ${g21 / 1e12:.2f} trillion to ", f"${g23 / 1e12:.2f} trillion",
        ".", "ok", "rounded", "holdout")
    add(tools, f"{c}'s GDP moved ", f"{abs((g23 - g21) / g21 * 100):.0f}%", " from 2021 to 2023.", "ok", "derived", "holdout")
    add(tools, f"Between 2021 and 2023, {c}'s economy grew from ${g21 / 1e12:.2f} trillion to ", f"${off(g23, 0.1, 0.2) / 1e12:.2f} trillion",
        ".", "bad", "fabricated", "holdout")
    add(tools, f"{c}'s GDP moved ", f"{abs((g23 - g21) / g21 * 100) + rng.choice([-1, 1]) * rng.uniform(4, 9):.0f}%",
        " from 2021 to 2023.", "bad", "bad_math", "holdout")

(HERE / "holdout.jsonl").write_text("\n".join(json.dumps(c) for c in cases) + "\n")
from collections import Counter
print(len(cases), Counter((c["label"], c["form"]) for c in cases))
