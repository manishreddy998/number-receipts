"""Score number-receipts and two baselines on bench/cases.jsonl. Writes bench/RESULTS.md.

Baselines
  string match   the number, as written, appears among the numbers in the tool output (exact value)
  rounding set   the check I shipped in transit-work-ledger: every tool number plus its rounding to 0 and 1
                 decimals; a claimed number passes if it is in that set
A checker should PASS every correct number and FLAG every wrong one. For swapped and wrong-metric numbers we also
report whether it named the value the sentence should have used (a MISMATCH with the right expected value).
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from receipts import check, MISMATCH, UNSUPPORTED  # noqa: E402
from receipts.extract import extract  # noqa: E402

SET = "holdout2" if "--holdout2" in sys.argv else ("holdout" if "--holdout" in sys.argv else "cases")
cases = [json.loads(ln) for ln in (HERE / f"{SET}.jsonl").read_text().splitlines() if ln.strip()]


def raw_numbers(text):
    return {float(n.replace(",", "")) for n in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", text)}


def string_match(case, claim):
    return claim.value in raw_numbers(json.dumps(case["tools"])) or \
        (claim.scale == 1 and claim.value in raw_numbers(json.dumps(case["tools"])))


def rounding_set(case, claim):
    seen = set()
    for v in raw_numbers(json.dumps(case["tools"])):
        seen |= {v, round(v), round(v, 1)}
    m = re.search(r"\d[\d,]*(?:\.\d+)?", claim.text)
    return float(m.group(0).replace(",", "")) in seen


def target_claim(case):
    claims = [c for c in extract(case["answer"]) if c.start <= case["target_start"] < c.end + 1 or
              c.start == case["target_start"] or case["target"].startswith(c.text) and abs(c.start - case["target_start"]) <= 1]
    return claims[0] if claims else None


rows = defaultdict(lambda: defaultdict(lambda: [0, 0]))
named = [0, 0]
misses = []
for case in cases:
    claim = target_claim(case)
    if claim is None:
        misses.append((case["id"], "target not extracted", case["answer"]))
        continue
    report = check(case["answer"], case["tools"])
    finding = next(f for f in report.findings if f.claim.start == claim.start)
    flagged = finding.verdict in (MISMATCH, UNSUPPORTED)
    for name, flag in (("number-receipts", flagged), ("string match", not string_match(case, claim)),
                       ("rounding set", not rounding_set(case, claim))):
        right = flag if case["label"] == "bad" else not flag
        rows[name][(case["label"], case["form"])][0] += right
        rows[name][(case["label"], case["form"])][1] += 1
    if (case["label"] == "bad") != flagged:
        misses.append((case["id"], f"{case['label']}/{case['form']} -> {finding.verdict}", case["answer"]))
    if case["form"] in ("swapped", "wrong_metric") and case["label"] == "bad":
        named[1] += 1
        named[0] += finding.verdict == MISMATCH and finding.expected is not None

forms = [("ok", f) for f in ("exact", "rounded", "hedged", "derived", "count")] + \
        [("bad", f) for f in ("fabricated", "swapped", "wrong_metric", "transposed", "bad_math", "wrong_scale")]
names = ["number-receipts", "string match", "rounding set"]
lines = ["| Numbers in the answer | Cases | " + " | ".join(names) + " |", "|---|---:|" + "---:|" * len(names)]
for label, form in forms:
    n = rows[names[0]][(label, form)][1]
    if not n:
        continue
    what = ("correct, " if label == "ok" else "wrong, ") + form.replace("_", " ")
    cells = [f"{rows[x][(label, form)][0] / n:.0%}" for x in names]
    lines.append(f"| {what} | {n} | " + " | ".join(cells) + " |")
for label, title in (("ok", "**Correct numbers passed**"), ("bad", "**Wrong numbers caught**")):
    tot = {x: [sum(v[0] for k, v in rows[x].items() if k[0] == label), sum(v[1] for k, v in rows[x].items() if k[0] == label)]
           for x in names}
    lines.append(f"| {title} | {tot[names[0]][1]} | " + " | ".join(f"**{tot[x][0] / tot[x][1]:.0%}**" for x in names) + " |")
table = "\n".join(lines)
summary = (f"{len(cases)} cases. Swapped or wrong-metric numbers reported as MISMATCH with the value the sentence should "
           f"have used: {named[0]}/{named[1]}.")
(HERE / f"RESULTS_{SET}.md").write_text(f"# Benchmark results ({SET})\n\n" + table + "\n\n" + summary + "\n")
print(table)
print(summary)
if "-v" in sys.argv:
    for m in misses:
        print(m)
