"""Find the numbers a piece of text claims, and how precisely each one was stated.

A claim keeps what a reader would take from it: the value, its unit (plain, percent, percentage points, a
multiplier), the scale it was written at ("1.2M"), how many digits were shown, and whether it was hedged
("about", "over", "under"). Precision matters: "1.2M" promises less than "1,184,302", and the checker must not
punish rounding that the writer was entitled to do.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9,
          "billion": 1e9, "t": 1e12, "tn": 1e12, "trillion": 1e12}
APPROX = ("about", "around", "approximately", "approx", "roughly", "nearly", "almost", "close to", "some", "~")
AT_LEAST = ("more than", "over", "above", "at least", "greater than", "exceeding", "upwards of", "north of")
AT_MOST = ("less than", "under", "below", "at most", "fewer than", "up to", "no more than")
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"

NUMBER = re.compile(r"""
    (?P<open>\()?
    (?P<sign>[-−+])?
    (?P<cur>CA\$|C\$|US\$|A\$|\$|€|£)?
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)
    (?P<close>\))?
    (?P<sp>\s?)
    (?P<suffix>%|percent\b|per\s?cent\b|percentage\s+points?\b|pp\b|bps\b|basis\s+points?\b|x\b|×|times\b|
               trillion\b|billion\b|million\b|thousand\b|tn\b|bn\b|mn\b|[kKmMbBtT]\b)?
""", re.X | re.I)

# Spans that look numeric but are not quantities: dates, times, versions, codes, URLs.
NOT_QUANTITIES = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s?(?:am|pm)?\b", re.I),
    re.compile(r"\b" + MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?\b(?:,?\s+\d{4})?", re.I),
    re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + MONTHS + r"(?:\s+\d{4})?", re.I),
    re.compile(r"\b(?:Q[1-4]|H[12]|FY|v|V)\s?\d+(?:\.\d+)*\b"),
    re.compile(r"https?://\S+"),
    re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.I),
    re.compile(r"(?m)^\s*\d{1,2}[.)]\s"),               # list markers
    re.compile(r"\b[A-Za-z]+\d+[A-Za-z\d]*\b"),          # codes such as A320, PO7731
    re.compile(r"\+?\d[\d\s().-]{8,}\d"),                # phone numbers
]

STOP = set("""a an the of in on at to for from by with and or but is are was were be been being it its this that
these those as than then so such per each every their there here which who whom what when where how why our your
his her they them we you i me my mine yours ours also only just about around nearly almost over under more less
most least up down into out across between among while had has have do does did not no yes vs versus""".split())


def tokens(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z]+|\d+(?:\.\d+)?", text.lower()) if t not in STOP]


def stem(word: str) -> str:
    if len(word) <= 3 or word.endswith("ss"):
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "shes", "ches", "xes", "zes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


@dataclass
class Claim:
    text: str                 # exactly as written, e.g. "$1.2M"
    value: float              # in base units; percents in percent units (27% -> 27.0)
    kind: str                 # number | percent | pp | multiplier
    decimals: int             # digits shown after the point
    scale: float              # 1, 1e3, 1e6 ...
    hedge: str                # exact | approx | at_least | at_most
    start: int
    end: int
    currency: str = ""
    near: list[str] = field(default_factory=list)       # words in the same clause
    sentence: list[str] = field(default_factory=list)   # words in the whole sentence
    base: str = ""                                       # what follows "from" in "up 12% from 2022", if anything
    left: list[str] = field(default_factory=list)       # clause words before the number, in order
    right: list[str] = field(default_factory=list)      # clause words after it

    @property
    def floor(self) -> float:
        """Half a unit of the last digit shown: the rounding any writer is entitled to."""
        return 0.5 * 10 ** -self.decimals * self.scale

    def tolerance(self) -> float:
        digits = self.text_digits()
        trailing = len(digits) - len(digits.rstrip("0")) if self.decimals == 0 else 0
        loose = 0.5 * 10 ** trailing * self.scale if self.decimals == 0 else self.floor   # "1,000" may be rounded
        cap = abs(self.value) * (0.10 if self.hedge == "approx" else 0.025)
        return max(self.floor, min(loose, cap)) + 1e-9 * max(1.0, abs(self.value))

    def text_digits(self) -> str:
        m = re.search(r"\d[\d,]*(?:\.\d+)?|\.\d+", self.text)
        return m.group(0).replace(",", "").split(".")[0] if m else ""

    def accepts(self, candidate: float) -> bool:
        tol = self.tolerance()
        if self.hedge == "at_least":
            return candidate >= self.value - self.floor and candidate <= max(self.value * 1.5, self.value + tol)
        if self.hedge == "at_most":
            return candidate <= self.value + self.floor and candidate >= min(self.value / 1.5, self.value - tol)
        return abs(candidate - self.value) <= tol


def _mask(text: str) -> str:
    out = list(text)
    for pattern in NOT_QUANTITIES:
        for m in pattern.finditer(text):
            for i in range(m.start(), m.end()):
                if not text[i].isspace():
                    out[i] = "#"
    return "".join(out)


def _hedge(before: str) -> str:
    b = before.lower().rstrip()
    for words, label in ((AT_LEAST, "at_least"), (AT_MOST, "at_most"), (APPROX, "approx")):
        if any(b.endswith(w) for w in words):
            return label
    return "exact"


def _sentences(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n\s*\n|\n(?=\s*[-*•])", text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return spans


def extract(text: str) -> list[Claim]:
    masked = _mask(text)
    found: list[Claim] = []
    for m in NUMBER.finditer(masked):
        raw_num = m.group("num")
        before = masked[max(0, m.start() - 1): m.start()]
        num_end = m.end("num") + (1 if m.group("close") else 0)
        after = masked[num_end: num_end + 1]
        if before and (before.isalnum() or before in "#._/") or "#" in m.group(0):
            continue
        suffix = (m.group("suffix") or "").strip()
        single = len(suffix) == 1 and suffix.lower() in SCALES
        if single and m.group("sp"):                      # "5 m" is metres, not millions
            suffix = ""
        end = m.start("suffix") + len(suffix) if suffix else num_end
        if not suffix and after and after.isalpha():
            continue
        number = float(raw_num.replace(",", ""))
        decimals = len(raw_num.split(".")[1]) if "." in raw_num else 0
        has_cur = bool(m.group("cur"))
        if (not suffix and not has_cur and decimals == 0 and "," not in raw_num and 1900 <= number <= 2100):
            continue                                       # a year
        kind, scale = "number", 1.0
        s = suffix.lower()
        if s.startswith("percentage") or s == "pp":
            kind = "pp"
        elif s in ("%", "percent") or s.startswith("per"):
            kind = "percent"
        elif s.startswith("basis") or s == "bps":
            kind, number, decimals = "pp", number / 100, decimals + 2
        elif s in ("x", "×") or (s == "times" and re.match(
                r"\s+(more|larger|bigger|higher|greater|faster|slower|less|smaller|as|the|that|what|its|their)\b",
                text[m.end():m.end() + 12], re.I)):
            kind = "multiplier"
        elif s == "times":                                  # "broke down 60 times" is a count
            end = num_end
        elif s in SCALES:
            scale = SCALES[s]
        negative = bool(m.group("sign") and m.group("sign") in "-−") or bool(m.group("open") and m.group("close"))
        start = m.start("cur") if has_cur else m.start("num")
        if m.group("sign"):
            start = m.start("sign")
        found.append(Claim(text=text[start:end], value=(-1 if negative else 1) * number * scale, kind=kind,
                           decimals=decimals, scale=scale, hedge=_hedge(text[max(0, start - 30): start]),
                           start=start, end=end, currency=m.group("cur") or ""))
    _attach_context(text, found)
    return found


def _attach_context(text: str, claims: list[Claim]) -> None:
    for s0, s1 in _sentences(text):
        inside = [c for c in claims if s0 <= c.start < s1]
        sentence_tokens = tokens(text[s0:s1])
        base = re.search(r"\bfrom\s+(?:the\s+|its\s+|their\s+)?([A-Za-z0-9]+)", text[s0:s1])
        for i, c in enumerate(inside):
            c.base = stem(base.group(1).lower()) if base else ""
            # The clause starts at the previous number itself (it is often a name: "Bus 1233 had 52 faults",
            # "501 Queen lost 942"), plus the word right before it.
            if i:
                prev = inside[i - 1]
                word = re.search(r"([A-Za-z]+)\s*$", text[s0:prev.start])
                left = prev.start - (len(text[s0:prev.start]) - word.start(1)) if word else prev.start
            else:
                left = s0
            right = inside[i + 1].start if i + 1 < len(inside) else s1
            # The clause around a number runs from the previous number to the next one, cut at clause breaks.
            seg_left = text[left:c.start]
            cut = max(seg_left.rfind(","), seg_left.rfind(";"), seg_left.rfind(" while "), seg_left.rfind(" and "))
            if i and cut >= 0 and re.search(r"[A-Za-z]{2,}", seg_left[cut + 1:]):
                seg_left = seg_left[cut + 1:]       # only cut if words are left after the break
            seg_right = text[c.end:right]
            cut = min([p for p in (seg_right.find(","), seg_right.find(";"), seg_right.find(" and ")) if p >= 0],
                      default=len(seg_right))
            c.left, c.right = tokens(seg_left), tokens(seg_right[:cut])
            c.near = c.left + c.right
            c.sentence = sentence_tokens
