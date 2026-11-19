# number-receipts

**Every number your AI agent says needs a receipt.**

An agent calls its tools, gets the right numbers back, and then writes prose. The prose is where numbers go wrong:
a real value attached to the wrong route or customer, the right row but the wrong field, arithmetic done on the
wrong base, or a figure nobody returned at all. In finance and operations a number the model "remembers" is a bug.

`number-receipts` checks every number in an answer against what the tools actually returned, deterministically, and
gives each one a receipt: the tool, the field, the row, and the arithmetic. Or it says exactly why there is none.

```bash
pip install git+https://github.com/manishreddy998/number-receipts
python -m receipts check examples/ttc_agent_transcript.json
```

```
≈ 2,711   DERIVED     sum of lost_hours over 3 rows = 2711.4  (rounded)
✓ 504     VERIFIED    lost_time_by_route.route[504 King streetcar] = 504  (identifier)
✓ 998     VERIFIED    lost_time_by_route.lost_hours[504 King streetcar] = 997.7  (rounded)
≈ 55      DERIVED     lost_hours[504 King streetcar] - lost_hours[501 Queen streetcar] = 997.7 - 942.3  (rounded)
✓ 501     VERIFIED    lost_time_by_route.route[501 Queen streetcar] = 501  (identifier)
≈ 37%     DERIVED     [weak] lost_hours[504 King streetcar] / sum of lost_hours = 997.7 / 2711.4  (rounded)
✓ 27%     VERIFIED    lost_time_by_route.pct_within_ttc_control[504 King streetcar] = 27
✓ 52      VERIFIED    lost_time_by_route_bus.route[52 Lawrence West bus] = 52  (identifier)
✗ 702     MISMATCH    lost_time_by_route_bus.lost_hours[52 Lawrence West bus] is 641.7
✓ 1233    VERIFIED    repeat_fault_vehicles.vehicle_number[1233 bus] = 1,233  (identifier)
✓ 60      VERIFIED    repeat_fault_vehicles.equipment_faults[1233 bus] = 60
✓ 54      VERIFIED    repeat_fault_vehicles.repeat_faults[1233 bus] = 54
? 3,400   UNSUPPORTED   (no tool value or simple arithmetic on tool values gives this number)
FAIL: 8 verified, 3 derived, 1 mismatch, 1 unsupported
```

That is a real agent-style answer about Toronto transit, checked against the real tool outputs it was written from.
The command exits with 1, so it can gate CI.

## Why not just search for the number, or ask another model?

| | Searching tool output for the number | Asking an LLM judge | number-receipts |
|---|---|---|---|
| "998 hours" when the tool said 997.7 | false alarm | usually passes | passes, rounding to the digits shown |
| "55 more hours than Queen" | false alarm | usually passes | passes, shows `997.7 - 942.3` |
| 942 hours for 504 King (942.3 is 501 Queen's) | **passes** | sometimes caught | **MISMATCH**, names both rows |
| 27% of planned hours (the field says 0.27, and 27 is another field in the same row) | **passes** | sometimes caught | **MISMATCH**, names both fields |
| Same input, same verdict, every run | yes | no | yes |
| Cost per check | free | one model call | free, about a millisecond |

General evaluation tools (RAGAS, DeepEval, TruLens) score whether a whole claim is supported, using a model or text
similarity. A sentence that sounds right with one wrong number in it can pass. This library only does numbers, and
does them exactly.

## Verdicts

| | Verdict | Meaning |
|---|---|---|
| ✓ | VERIFIED | a tool returned this value, allowing the rounding the writer used ("1.2M", "998", "about 1,000") |
| ≈ | DERIVED | it follows from tool values by arithmetic: sum, difference, average, ratio, percent change, share of total, count, "3x" |
| ✗ | MISMATCH | the sentence is about a value a tool did return, and the number is wrong. The report shows the right value |
| ? | UNSUPPORTED | nothing any tool returned produces it |

MISMATCH is the one that matters most. A made-up number is bad. A real number attached to the wrong row looks
verified to any check that only asks "does this number appear somewhere?".

## How it decides

1. **Reads numbers the way a person writes them.** `$1.2M`, `2.19 trillion`, `27%`, `3.5 percentage points`,
   `40 bps`, `2.5x`, `about 1,000`, `over 50`, `(4.5%)`. Skips what is not a quantity: years, dates, times, `Q4`,
   `v2.1`, `PO7731`, list markers, phone numbers.
2. **Respects precision.** `$4.53 trillion` may differ from the source by half of the last digit shown
   (0.005 trillion), not by 0.5 trillion. `about` loosens it, `over` and `under` become bounds.
3. **Indexes tool output with provenance.** JSON, lists of rows, CSV, markdown tables or plain text. Every number
   keeps its path, its field name, the row it sits in ("504 King streetcar") and whether the field already holds a
   percent (`pct_of_planned_lost: 0.27` is 0.27%, not 27%).
4. **Finds the arithmetic, but only arithmetic that makes sense.** Operands must be the same field across rows of one
   table (sums, differences, changes, shares) or two fields of one row (ratios), and only rows the sentence names.
   "Up 12% from 2022" uses 2022 as the base. This is what keeps coincidences out: with 24 GDP figures, some pair
   divides to almost any percentage.
5. **Decides what each number is about.** It reads the words around the number (the name right before it counts
   most), matches them to row names and field names, and picks the one value the sentence is talking about. If that
   value disagrees with the number, it is a MISMATCH, even when the number happens to exist elsewhere.

No dependencies. Pure Python, 3.10+.

## Results

Labeled cases built from real tool outputs (Toronto transit delays and World Bank GDP), with correct numbers in five
forms and wrong numbers in six. Two baselines: searching the tool output for the number, and the rounding check I
shipped in [transit-work-ledger](https://github.com/manishreddy998/transit-work-ledger) before writing this.

| Set | Cases | Correct numbers passed | Wrong numbers caught | String match (passed / caught) | Rounding set (passed / caught) |
|---|---:|---:|---:|---:|---:|
| Held-out 2, **first and only run before its fix** | 123 | **99%** | **78%** | 65% / 72% | 65% / 72% |
| Held-out 2, after fixing "A vs B" comparisons | 123 | 100% | 96% | 65% / 72% | 65% / 72% |
| Held-out 1, first run | 114 | 100% | 76% | 54% / 71% | 62% / 61% |
| Held-out 1, after fixing bullet lists and leading clauses | 114 | 97% | 92% | 54% / 71% | 62% / 61% |
| Development set (tuned on) | 240 | 100% | 100% | 46% / 69% | 53% / 69% |

Swapped-row and wrong-field numbers come back as MISMATCH with the value the sentence should have used in 49/49
(dev), 19/19 and 18/18 (held-out, after fixes). Per-form tables are in `bench/RESULTS_*.md`.

How to read this honestly: the development set was used to build the checker, so 100% there means little. Each
held-out set was written after the previous round of changes, run once, and its first score is in the table. The
fixes those runs exposed are real weaknesses that are now handled, and the "after" rows are no longer held out.
The cases are templates over real data, not transcripts sampled from a live model. Running it over real agent logs
is the next step, and a PR with anonymised transcripts is very welcome.

```bash
python bench/build.py && python bench/run.py                 # development set
python bench/run.py --holdout && python bench/run.py --holdout2
```

## Use it

```python
from receipts import check

report = check(answer, {"lost_time_by_route": rows})     # or a list of outputs, JSON strings, CSV, text
report.passed()            # False if any number is MISMATCH or UNSUPPORTED
print(report.to_text())    # the receipts
report.to_dict()           # for logs and dashboards
report.redact()            # the answer with unverified numbers replaced, safe to show a user
```

Before an answer leaves your system:

```python
from receipts.adapters import guard
answer = guard(answer, tool_outputs, on_fail="raise")    # or "redact", or "annotate" for a review queue
```

From a transcript (Anthropic Messages, OpenAI Chat, LangChain/LangGraph messages, no SDK needed):

```python
from receipts.adapters import check_transcript, langgraph_node
report = check_transcript(messages)
graph.add_node("receipts", langgraph_node)               # wire it right before END
```

In CI, over logged runs:

```bash
python -m receipts check runs.jsonl            # exit 1 if any number has no receipt
python -m receipts check runs.jsonl --strict   # also fail on weak, value-only matches
```

## Honest limits

- It checks that numbers are faithful to the tools, not that the tools are right. A wrong query gives a confident receipt.
- English only. Numbers written as words ("twelve", "a third") are not read.
- A receipt shows one valid derivation. If two different calculations give the same number, it may show a different
  one than the writer used.
- Percent versus fraction is decided from field names (`pct_`, `percent`, `rate`, `share`). Badly named fields can
  fool it, and the report will say what it assumed.
- Rows told apart only by a date (one event per day) are matched less reliably than rows with names.
- Context is lexical. "the King line" and "504" connect only through words or codes the row actually carries.

## Layout

```
receipts/extract.py    numbers, units, scale, precision and hedges, plus the words around each one
receipts/evidence.py   tool output of any shape into numbers with path, field, row and unit
receipts/core.py       receipts, allowed arithmetic, what each number is about, verdicts and reports
receipts/adapters.py   transcripts (Anthropic, OpenAI, LangChain), guard(), a LangGraph node
receipts/__main__.py   command line, exit code for CI
bench/                 fixtures from real data, case builders, held-out sets, the scorer
tests/                 unit tests, transcript tests and a benchmark floor
examples/              an agent transcript about Toronto transit
```

Data: City of Toronto Open Data (TTC delay data and GTFS, Open Government Licence - Toronto), via
[transit-work-ledger](https://github.com/manishreddy998/transit-work-ledger), and World Bank World Development
Indicators (GDP, current US$, CC BY 4.0).

---

Built by Manish Reddy, Data/AI Engineer in Toronto. [LinkedIn](https://www.linkedin.com/in/manish-re-50c02a719k/) · [GitHub](https://github.com/manishreddy998)
