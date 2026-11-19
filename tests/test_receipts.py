import json
from pathlib import Path

import pytest

from receipts import DERIVED, MISMATCH, UNSUPPORTED, VERIFIED, check, extract
from receipts.adapters import UnverifiedNumbers, check_transcript, guard

FIX = Path(__file__).parent.parent / "bench" / "fixtures"
TTC = json.loads((FIX / "ttc_tools.json").read_text())
ROUTES = {"lost_time_by_route": TTC["lost_time_by_route"]}
GDP = json.loads((FIX / "worldbank_gdp.json").read_text())


def verdict(answer, tools, text):
    report = check(answer, tools)
    return next(f for f in report.findings if f.claim.text == text)


# ---------------------------------------------------------------- what counts as a number

def test_skips_years_dates_times_codes_and_list_markers():
    found = [c.text for c in extract("1. On Nov 19, 2026 at 10:30 am, PO7731 for Q4 2025 (v2.1) cost $1.2M.")]
    assert found == ["$1.2M"]


@pytest.mark.parametrize("text,value,kind,hedge", [
    ("$1.2M", 1.2e6, "number", "exact"), ("about 1,000 hours", 1000, "number", "approx"),
    ("over 50 faults", 50, "number", "at_least"), ("27%", 27, "percent", "exact"),
    ("3.5 percentage points", 3.5, "pp", "exact"), ("2.5x", 2.5, "multiplier", "exact"),
    ("$2.19 trillion", 2.19e12, "number", "exact"), ("40 bps", 0.4, "pp", "exact")])
def test_reads_units_scales_and_hedges(text, value, kind, hedge):
    c = extract(text)[0]
    assert c.value == pytest.approx(value) and c.kind == kind and c.hedge == hedge


def test_rounding_tolerance_follows_the_digits_shown():
    c = extract("$4.53 trillion")[0]
    assert c.accepts(4.534e12) and not c.accepts(4.562e12)
    assert extract("998 hours")[0].accepts(997.7)


# ---------------------------------------------------------------- verdicts on real tool output

def test_verified_with_rounding():
    f = verdict("The 504 King lost 998 hours.", ROUTES, "998")
    assert f.verdict == VERIFIED and "lost_hours" in f.receipt.formula


def test_derived_difference_share_and_change():
    answer = "504 King lost 55 more hours than 501 Queen, 37% of the 2,711 hours lost on these routes."
    assert verdict(answer, ROUTES, "55").verdict == DERIVED
    assert verdict(answer, ROUTES, "37%").verdict == DERIVED
    assert verdict(answer, ROUTES, "2,711").verdict == DERIVED
    f = verdict("Brazil's GDP was $2.19 trillion in 2023, up 12% from 2022.", GDP, "12%")
    assert f.verdict == DERIVED and "2022 Brazil" in f.receipt.formula and "2023 Brazil" in f.receipt.formula


def test_swapped_entity_is_a_mismatch_with_the_right_value():
    f = verdict("504 King lost 942 hours.", ROUTES, "942")
    assert f.verdict == MISMATCH and f.expected.value == 997.7 and "501 Queen" in f.note


def test_wrong_field_in_the_same_row_is_a_mismatch():
    f = verdict("504 King lost 27% of its planned hours.", ROUTES, "27%")
    assert f.verdict == MISMATCH and f.expected.key == "pct_of_planned_lost"


def test_made_up_number_is_unsupported():
    assert verdict("504 King lost 998 hours, 4.1% of planned service.", ROUTES, "4.1%").verdict == UNSUPPORTED


def test_arithmetic_only_uses_rows_the_sentence_names():
    # 12% is also UK GDP / US GDP in 2022, a coincidence that must not count for Japan
    assert verdict("Japan's GDP grew 12% from 2022 to 2023.", GDP, "12%").verdict in (MISMATCH, UNSUPPORTED)


def test_no_tool_called_means_nothing_is_verified():
    report = check("Revenue grew 14% to $3.2M.", [])
    assert not report.tools_called and all(f.verdict == UNSUPPORTED for f in report.findings)


# ---------------------------------------------------------------- transcripts and guards

def test_anthropic_transcript():
    msgs = [{"role": "user", "content": "How did 504 King do?"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "lost_time_by_route", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                          "content": json.dumps(TTC["lost_time_by_route"])}]},
            {"role": "assistant", "content": [{"type": "text", "text": "504 King lost 998 hours, 0.27% of plan."}]}]
    report = check_transcript(msgs)
    assert report.passed() and report.findings[-1].receipt.sources[0].tool == "lost_time_by_route"


def test_openai_transcript_flags_mismatch():
    msgs = [{"role": "assistant", "content": None,
             "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "routes", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": json.dumps(TTC["lost_time_by_route"])},
            {"role": "assistant", "content": "504 King lost 942 hours."}]
    assert not check_transcript(msgs).passed()


def test_guard_modes():
    answer = "504 King lost 998 hours and 1,240 more last week."
    with pytest.raises(UnverifiedNumbers):
        guard(answer, ROUTES)
    assert guard(answer, ROUTES, on_fail="redact") == "504 King lost 998 hours and [unverified] more last week."


# ---------------------------------------------------------------- the benchmark must not regress

def test_benchmark_floor():
    import subprocess, sys
    out = subprocess.run([sys.executable, "bench/run.py"], capture_output=True, text=True,
                         cwd=Path(__file__).parent.parent).stdout
    passed = [ln for ln in out.splitlines() if "Correct numbers passed" in ln][0]
    caught = [ln for ln in out.splitlines() if "Wrong numbers caught" in ln][0]
    assert "**100%**" in passed.split("|")[3] and "**100%**" in caught.split("|")[3]
