"""Give every number in an answer a receipt, or say exactly why it has none.

Verdicts
  VERIFIED     a tool returned this value (allowing the rounding the writer used)
  DERIVED      it follows from tool values by simple arithmetic, and the receipt shows the arithmetic
  MISMATCH     the answer is talking about a value a tool did return, and got it wrong
  UNSUPPORTED  nothing any tool returned produces it

MISMATCH is the dangerous one. A made-up number is bad. A real number attached to the wrong route, customer or
metric looks verified to every check that only asks "does this number appear somewhere?".
"""
from __future__ import annotations

import itertools
import json
from collections import defaultdict
from dataclasses import dataclass, field

from .evidence import RATIO_KEY, Evidence, build
from .extract import Claim, extract

VERIFIED, DERIVED, MISMATCH, UNSUPPORTED = "VERIFIED", "DERIVED", "MISMATCH", "UNSUPPORTED"
MARK = {VERIFIED: "✓", DERIVED: "≈", MISMATCH: "✗", UNSUPPORTED: "?"}


@dataclass
class Receipt:
    value: float
    formula: str
    sources: list[Evidence]
    how: str                 # direct | identifier | sum | difference | ratio | ...
    score: float = 0.0
    anchored: bool = False

    def to_dict(self):
        return {"value": round(self.value, 6), "formula": self.formula, "how": self.how,
                "sources": [e.path for e in self.sources]}


@dataclass
class Finding:
    claim: Claim
    verdict: str
    receipt: Receipt | None = None
    expected: Evidence | None = None
    note: str = ""
    confidence: str = "high"

    def to_dict(self):
        d = {"text": self.claim.text, "value": self.claim.value, "kind": self.claim.kind, "verdict": self.verdict,
             "confidence": self.confidence, "note": self.note}
        if self.receipt:
            d["receipt"] = self.receipt.to_dict()
        if self.expected:
            d["expected"] = {"value": self.expected.value, "path": self.expected.path}
        return d


@dataclass
class Report:
    answer: str
    findings: list[Finding] = field(default_factory=list)
    tools_called: bool = True

    def counts(self):
        c = defaultdict(int)
        for f in self.findings:
            c[f.verdict] += 1
        return dict(c)

    def passed(self, strict: bool = False) -> bool:
        bad = [f for f in self.findings if f.verdict in (MISMATCH, UNSUPPORTED)]
        weak = [f for f in self.findings if f.confidence == "low"] if strict else []
        return not bad and not weak

    @property
    def problems(self):
        return [f for f in self.findings if f.verdict in (MISMATCH, UNSUPPORTED)]

    def to_dict(self):
        return {"passed": self.passed(), "tools_called": self.tools_called, "counts": self.counts(),
                "findings": [f.to_dict() for f in self.findings]}

    def to_json(self, **kw):
        return json.dumps(self.to_dict(), **kw)

    def to_text(self) -> str:
        lines = []
        width = max([len(f.claim.text) for f in self.findings] + [6])
        for f in self.findings:
            if f.receipt:
                detail = f.receipt.formula
            elif f.expected:
                detail = f"{f.expected.label()} is {_fmt(f.expected.value)}"
            else:
                detail = ""
            tail = f"  ({f.note})" if f.note else ""
            low = " [weak]" if f.confidence == "low" and f.verdict in (VERIFIED, DERIVED) else ""
            lines.append(f"{MARK[f.verdict]} {f.claim.text:<{width}}  {f.verdict:<11}{low} {detail}{tail}".rstrip())
        c = self.counts()
        summary = ", ".join(f"{c[k]} {k.lower()}" for k in (VERIFIED, DERIVED, MISMATCH, UNSUPPORTED) if c.get(k))
        lines.append(("PASS" if self.passed() else "FAIL") + f": {summary or 'no numbers'}")
        return "\n".join(lines)

    def annotate(self) -> str:
        """The answer with each problem number marked inline."""
        out, last = [], 0
        for f in sorted(self.findings, key=lambda f: f.claim.start):
            out.append(self.answer[last:f.claim.end])
            if f.verdict in (MISMATCH, UNSUPPORTED):
                out.append(f" [{f.verdict.lower()}" + (f": expected {_fmt(f.expected.value)}" if f.expected else "") + "]")
            last = f.claim.end
        return "".join(out) + self.answer[last:]

    def redact(self, placeholder: str = "[unverified]") -> str:
        """The answer with every number that has no receipt replaced, safe to show a user."""
        out, last = [], 0
        for f in sorted(self.findings, key=lambda f: f.claim.start):
            if f.verdict in (MISMATCH, UNSUPPORTED):
                out.append(self.answer[last:f.claim.start] + placeholder)
                last = f.claim.end
        return "".join(out) + self.answer[last:]


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() and abs(v) >= 1000 else (f"{v:g}" if abs(v) < 1e6 else f"{v:,.0f}")


# ---------------------------------------------------------------- relevance: is this number about that field?

def relevance(claim: Claim, ev: Evidence) -> tuple[float, bool, bool]:
    near, sent = set(claim.near), set(claim.sentence)
    closest = set(claim.left[-3:])                      # the name right before a number is the one it belongs to
    row_near = sum(1 for t in set(ev.row_tokens) if t in near)
    row_sent = sum(1 for t in set(ev.row_tokens) if t in sent and t not in near)
    row_close = sum(1 for t in set(ev.row_tokens) if t in closest and not t.isdigit() and t not in ev.key_tokens)
    key_near = sum(1 for t in set(ev.key_tokens) if t in near)
    key_sent = sum(1 for t in set(ev.key_tokens) if t in sent and t not in near)
    score = 3 * row_near + 2 * row_close + 0.5 * row_sent + 1.5 * key_near + 0.75 * key_sent
    return score, row_near > 0 or (not ev.row_tokens and key_near > 0), (key_near + key_sent) > 0


def _compatible_direct(claim: Claim, ev: Evidence):
    """Values this piece of evidence can stand for, given the claim's unit."""
    if ev.is_id:
        return [(ev.value, "identifier", "")] if claim.kind == "number" else []
    if claim.kind == "number":
        return [] if ev.is_percent else [(ev.value, "direct", "")]
    if claim.kind == "percent":
        if ev.is_percent:
            return [(ev.value, "direct", "")]
        if RATIO_KEY.search(ev.key) and abs(ev.value) <= 1.5:
            return [(ev.value * 100, "direct", " x 100")]
        return []
    if claim.kind == "pp":
        return [(ev.value, "direct", "")] if ev.is_percent and "change" in ev.key.lower() else []
    if claim.kind == "multiplier":
        k = ev.key.lower()
        return [(ev.value, "direct", "")] if any(w in k for w in ("ratio", "multiple", "times", "_x")) else []
    return []


def _derived(claim: Claim, pool: list[Evidence], scores: dict[int, tuple]):
    """Arithmetic a writer could reasonably have done. Operands must belong together: the same field across rows
    (sums, differences, changes, shares) or two fields of the same row (ratios). This is what keeps coincidences out."""
    sentence = set(claim.sentence)

    row_numbers = {t for e in pool for t in e.row_tokens if t.isdigit()}
    said_numbers = row_numbers & sentence            # e.g. the years the sentence talks about

    def mentioned(e):
        """Rows the sentence names (by name, not just by year), or values in no row at all. If the sentence names
        years or codes that rows carry, a row must carry one of them too."""
        names = [t for t in e.row_tokens if not t.isdigit()] or e.row_tokens
        if names and not any(t in sentence for t in names):
            return False
        digits = {t for t in e.row_tokens if t.isdigit()}
        return not (digits and said_numbers and not digits & said_numbers)

    numeric = [e for e in pool if not e.is_id]
    by_key = defaultdict(list)
    for e in numeric:                    # arithmetic stays inside one table: a streetcar total never adds bus rows
        by_key[(e.table or e.tool, e.key, e.is_percent)].append(e)
    rec = []

    def add(value, formula, sources, how):
        s = [scores[id(e)][0] for e in sources]
        anchored = any(scores[id(e)][1] for e in sources)
        rec.append(Receipt(value, formula, sources, how, max(s) + 0.25 * (sum(s) - max(s)) - 1.0, anchored))

    for (_table, key, is_pct), group in by_key.items():
        if not key or len(group) < 2:
            continue
        rows = {e.row_id: e for e in group if e.row_id >= 0}
        col = list(rows.values()) or group
        if len(col) >= 2 and not is_pct:
            total = sum(e.value for e in col)
            if claim.kind == "number":
                add(total, f"sum of {key} over {len(col)} rows = {_fmt(total)}", col, "sum")
                add(total / len(col), f"average {key} over {len(col)} rows = {_fmt(total / len(col))}", col, "average")
            if claim.kind == "percent" and total:
                for e in [x for x in col if mentioned(x)]:
                    add(e.value / total * 100, f"{key}[{e.row}] / sum of {key} = {_fmt(e.value)} / {_fmt(total)}",
                        [e] + [x for x in col if x is not e], "share of total")
        ranked = sorted([e for e in col if mentioned(e)], key=lambda e: -scores[id(e)][0])[:12]
        for a, b in itertools.permutations(ranked, 2):
            fa, fb = f"{key}[{a.row}]", f"{key}[{b.row}]"
            if claim.kind == "number" and not is_pct and a.value >= b.value:
                add(a.value - b.value, f"{fa} - {fb} = {_fmt(a.value)} - {_fmt(b.value)}", [a, b], "difference")
                add(a.value + b.value, f"{fa} + {fb} = {_fmt(a.value)} + {_fmt(b.value)}", [a, b], "sum")
            if claim.kind == "pp" and is_pct and a.value >= b.value:
                add(a.value - b.value, f"{fa} - {fb} = {_fmt(a.value)} - {_fmt(b.value)} points", [a, b], "difference")
            base_named = claim.base and claim.base in set(a.row_tokens) | set(b.row_tokens)
            if claim.kind == "percent" and not is_pct and b.value and (not base_named or
                                                                     (claim.base in b.row_tokens and claim.base not in a.row_tokens)):
                change = (a.value - b.value) / abs(b.value) * 100
                add(abs(change) if claim.value >= 0 else change,
                    f"change from {fb} to {fa} = ({_fmt(a.value)} - {_fmt(b.value)}) / {_fmt(b.value)}", [a, b],
                    "percent change")
                add(a.value / b.value * 100, f"{fa} / {fb} = {_fmt(a.value)} / {_fmt(b.value)}", [a, b], "ratio")
            if claim.kind == "multiplier" and b.value and a.value >= b.value:
                add(a.value / b.value, f"{fa} / {fb} = {_fmt(a.value)} / {_fmt(b.value)}", [a, b], "ratio")
    if claim.kind == "number" and claim.decimals == 0:
        tables = defaultdict(set)
        for e in pool:
            if e.row_id >= 0 and e.table:
                tables[e.table].add(e.row_id)
        for table, ids in tables.items():
            first = next(e for e in pool if e.table == table)
            add(float(len(ids)), f"count of rows in {table} = {len(ids)}", [first], "count")
    by_row = defaultdict(list)
    for e in numeric:
        if e.row_id >= 0:
            by_row[e.row_id].append(e)
    for row in by_row.values():
        if not mentioned(row[0]):
            continue
        for a, b in itertools.permutations(row, 2):
            if not b.value or a.is_percent or b.is_percent:
                continue
            fa, fb = f"{a.key}[{a.row}]", f"{b.key}"
            if claim.kind == "percent":
                add(a.value / b.value * 100, f"{fa} / {fb} = {_fmt(a.value)} / {_fmt(b.value)}", [a, b], "ratio")
            if claim.kind == "multiplier" and a.value >= b.value:
                add(a.value / b.value, f"{fa} / {fb} = {_fmt(a.value)} / {_fmt(b.value)}", [a, b], "ratio")
            if claim.kind == "number" and a.value >= b.value:
                add(a.value - b.value, f"{fa} - {fb} = {_fmt(a.value)} - {_fmt(b.value)}", [a, b], "difference")
    return rec


# ---------------------------------------------------------------- the check

def check(answer: str, tool_outputs, *, derive: bool = True) -> Report:
    """Check every number in `answer` against `tool_outputs` (list, dict of name -> output, or (name, output) pairs)."""
    claims = extract(answer)
    evidence = build(tool_outputs or [])
    report = Report(answer=answer, tools_called=bool(evidence))
    for claim in claims:
        report.findings.append(_judge(claim, evidence, derive))
    if not report.tools_called:
        for f in report.findings:
            f.note = "no tool returned anything in this turn"
    return report


def _judge(claim: Claim, evidence: list[Evidence], derive: bool) -> Finding:
    if not evidence:
        return Finding(claim, UNSUPPORTED)
    scores = {id(e): relevance(claim, e) for e in evidence}
    candidates = []
    for e in evidence:
        for value, how, suffix in _compatible_direct(claim, e):
            s, anchored, _ = scores[id(e)]
            candidates.append(Receipt(value, f"{e.label()} = {_fmt(e.value)}{suffix}", [e], how, s, anchored))
    for e in evidence:                              # numbers named inside a row label ("route 504", "bus 1233")
        if claim.kind == "number" and claim.decimals == 0 and str(int(claim.value)) in e.row_tokens:
            candidates.append(Receipt(claim.value, f"named in {e.tool} row [{e.row}]", [e], "identifier", 1.0, True))
            break
    direct_hit = [r for r in candidates if _accepts(claim, r)]
    if derive and not any(r.anchored for r in direct_hit):
        candidates += _derived(claim, evidence, scores)
    hits = [r for r in candidates if _accepts(claim, r)]
    direct = max((r for r in hits if r.how in ("direct", "identifier")), key=lambda r: (r.anchored, r.score), default=None)
    derived = max((r for r in hits if r.how not in ("direct", "identifier")), key=lambda r: (r.anchored, r.score),
                  default=None)
    best = direct if direct and (direct.anchored or not derived or direct.score >= derived.score - 2) else derived

    anchor = _anchor(claim, evidence, scores)
    if best and best.how == "identifier":
        return Finding(claim, VERIFIED, best, note="identifier")
    if anchor and not _accepts_value(claim, anchor) and (best is None or scores[id(anchor)][0] > best.score + 1):
        note = ""
        if best:
            src = best.sources[0]
            note = f"{best.value:g} is {src.label()}" if best.how == "direct" else f"{best.value:g} = {best.formula}"
        return Finding(claim, MISMATCH, expected=anchor, note=note)
    if best:
        verdict = VERIFIED if best.how == "direct" else DERIVED
        confidence = "high" if best.anchored or best.score >= 1.5 else "low"
        note = "" if abs(best.value - claim.value) < 1e-9 * max(1, abs(claim.value)) or claim.hedge != "exact" \
            else "rounded"
        if claim.hedge != "exact":
            note = claim.hedge.replace("_", " ")
        return Finding(claim, verdict, best, note=note, confidence=confidence)
    return Finding(claim, UNSUPPORTED, note="no tool value or simple arithmetic on tool values gives this number")


def _accepts(claim: Claim, r: Receipt) -> bool:
    return claim.accepts(r.value)


def _accepts_value(claim: Claim, e: Evidence) -> bool:
    return any(claim.accepts(v) for v, _, _ in _compatible_direct(claim, e))


def _anchor(claim: Claim, evidence: list[Evidence], scores) -> Evidence | None:
    """The single tool value the sentence is most clearly talking about, if there is one: same row named nearby,
    and the same metric named in the sentence."""
    fields_in_row = defaultdict(set)
    for e in evidence:
        if not e.is_id and e.row_id >= 0 and _compatible_direct(claim, e):
            fields_in_row[e.row_id].add(e.key)
    near = set(claim.near)
    metric_words = {t for e in evidence for t in e.key_tokens}
    sentence_row = _sentence_row(claim, evidence)
    best, best_score = None, 0.0
    adjusted = {}
    for e in evidence:
        if e.is_id or not _compatible_direct(claim, e):
            continue
        s, anchored, metric = scores[id(e)]
        named = any(t in near for t in e.row_tokens if not t.isdigit()) or (e.row_id == sentence_row and e.row_id >= 0)
        if any(t in set(claim.left[-3:]) for t in e.row_tokens if not t.isdigit() and t not in metric_words):
            s += 2
        anchored = anchored or named
        only_field = len(fields_in_row.get(e.row_id, ())) == 1
        if e.row_id == sentence_row and e.row_id >= 0:
            s += 3                                   # the row this sentence (or bullet) is about
        adjusted[id(e)] = s
        if anchored and named and (metric or only_field) and e.row_tokens and s > best_score:
            best, best_score = e, s
    if best is None:
        return None
    rivals = [e for e in evidence if e is not best and not e.is_id and e.row_id != sentence_row
              and e.row_id != best.row_id and adjusted.get(id(e), -1) >= best_score and _compatible_direct(claim, e)
              and e.value != best.value]
    return None if rivals else best


def _sentence_row(claim: Claim, evidence: list[Evidence]) -> int:
    """If the sentence clearly names exactly one row (most of its name words appear), return that row's id.
    Bullet lists name the row once ("- duplicate log lines: 386 events (0.21%)") and every number after it
    belongs to that row."""
    sentence = set(claim.sentence)
    best, best_hits, tie = -1, 0.0, False
    seen = set()
    for e in evidence:
        if e.row_id < 0 or e.row_id in seen:
            continue
        seen.add(e.row_id)
        names = [t for t in dict.fromkeys(e.row_tokens) if not t.isdigit() and len(t) > 1]
        if not names:
            continue
        hits = sum(t in sentence for t in names)
        share = hits / len(names)
        if hits >= 2 and share >= 0.5 or hits >= 1 and share == 1:
            if hits > best_hits:
                best, best_hits, tie = e.row_id, hits, False
            elif hits == best_hits:
                tie = True
    return -1 if tie else best
