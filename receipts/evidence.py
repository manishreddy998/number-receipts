"""Turn whatever the tools returned into a flat list of numbers that know where they came from.

Tool outputs arrive as JSON strings, dicts, lists of rows, CSV or markdown tables, or plain text. Every number
becomes an Evidence item carrying its path, its field name, the row it sits in (so "504 King" travels with
"lost_hours: 997.7") and whether the field already holds a percent.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field

from .extract import extract, tokens

PERCENT_KEY = re.compile(r"(^|_)(pct|percent|percentage)(_|$)|_pct$|pct_", re.I)
RATIO_KEY = re.compile(r"(ratio|share|rate|fraction|proportion|margin)", re.I)
ID_KEY = re.compile(r"((^|_)(id|number|no|num|code|zip|postal|sku)$)|^(route|vehicle|year|account|line)$", re.I)


@dataclass
class Evidence:
    value: float
    path: str                  # e.g. lost_time_by_route[0].lost_hours
    key: str                   # field name, "" for free text
    tool: str
    row: str = ""              # label of the row, e.g. "504 King"
    row_id: int = -1           # which row (for arithmetic within a row)
    table: str = ""            # which list it belongs to (for arithmetic across rows)
    is_percent: bool = False   # value is already in percent units
    is_id: bool = False        # an identifier, only ever matched exactly
    key_tokens: list[str] = field(default_factory=list)
    row_tokens: list[str] = field(default_factory=list)

    def label(self) -> str:
        where = f"[{self.row}]" if self.row else ""
        return f"{self.tool}.{self.key or 'text'}{where}"


def _key_tokens(key: str) -> list[str]:
    return tokens(re.sub(r"[_\-.]", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", key)))


def _parse(raw):
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw).strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 3 and lines[0].count("|") >= 2 and set(lines[1].replace("|", "").strip()) <= set("-: "):
        head = [h.strip() for h in lines[0].strip("|").split("|")]
        return [dict(zip(head, [c.strip() for c in ln.strip("|").split("|")])) for ln in lines[2:]]
    if len(lines) >= 2 and lines[0].count(",") >= 1 and all(ln.count(",") == lines[0].count(",") for ln in lines[:5]):
        return list(csv.DictReader(io.StringIO(text)))
    return text


def _as_number(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = re.fullmatch(r"([-+]?)\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?(%?)", s)
    if not m:
        return None
    return float((m.group(1) + m.group(2)).replace(",", "") + (m.group(3) or "")), bool(m.group(4))


def build(tool_outputs) -> list[Evidence]:
    """tool_outputs: list of outputs, or list of (tool_name, output), or dict {tool_name: output}."""
    if isinstance(tool_outputs, dict):
        items = list(tool_outputs.items())
    else:
        items = [(o[0], o[1]) if isinstance(o, tuple) and len(o) == 2 else (f"tool{i}", o)
                 for i, o in enumerate(tool_outputs)]
    out: list[Evidence] = []
    counter = [0]
    for name, raw in items:
        _walk(_parse(raw), str(name), str(name), out, counter, row="", row_id=-1, row_tokens=[], table="")
    return out


def _row_label(d: dict) -> tuple[str, list[str]]:
    parts = []
    for k, v in d.items():
        if isinstance(v, str) and v.strip() and _as_number(v) is None and len(v) <= 40:
            parts.append(v.strip())
        elif ID_KEY.search(str(k)) and isinstance(v, (str, int)) and not isinstance(v, bool):
            parts.insert(0, str(v))
    toks = tokens(" ".join(dict.fromkeys(parts)))      # dates still help tell rows apart
    shown = [p for p in parts if not re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", p)] or parts
    label = " ".join(dict.fromkeys(shown))[:60]
    for name in parts:                       # "United States" also goes by "US"
        words = re.findall(r"[A-Za-z]+", name)
        if len(words) >= 2 and all(w[0].isupper() for w in words):
            toks.append("".join(w[0] for w in words).lower())
    return label, toks


def _walk(node, path, tool, out, counter, row, row_id, row_tokens, table):
    if isinstance(node, dict):
        label, toks = _row_label(node)
        if label:
            counter[0] += 1
            row, row_id, row_tokens = label, counter[0], toks
        for k, v in node.items():
            sub = f"{path}.{k}"
            if isinstance(v, (dict, list)):
                _walk(v, sub, tool, out, counter, row, row_id, row_tokens, f"{table}.{k}" if table else k)
                continue
            parsed = _as_number(v)
            if parsed is None:
                if isinstance(v, str) and len(v) > 40:
                    _text(v, sub, tool, out)
                continue
            value, had_pct = parsed if isinstance(parsed, tuple) else (parsed, False)
            is_id = bool(ID_KEY.search(k)) and (isinstance(v, str) or float(value).is_integer())
            out.append(Evidence(value=value, path=sub, key=k, tool=tool, row=row, row_id=row_id, table=table,
                                is_percent=had_pct or bool(PERCENT_KEY.search(k)), is_id=is_id,
                                key_tokens=_key_tokens(k), row_tokens=row_tokens))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{path}[{i}]", tool, out, counter, row if not isinstance(item, dict) else "",
                  row_id if not isinstance(item, dict) else -1, row_tokens if not isinstance(item, dict) else [],
                  table or path)
    elif isinstance(node, str):
        _text(node, path, tool, out)
    else:
        parsed = _as_number(node)
        if parsed is not None:
            value = parsed[0] if isinstance(parsed, tuple) else parsed
            out.append(Evidence(value=value, path=path, key="", tool=tool, row=row, row_id=row_id, table=table))


def _text(text, path, tool, out):
    for c in extract(text):
        out.append(Evidence(value=c.value, path=f"{path}@{c.start}", key="", tool=tool,
                            is_percent=c.kind in ("percent", "pp"), key_tokens=c.near, row_tokens=[]))
