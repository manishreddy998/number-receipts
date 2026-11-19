"""Read agent transcripts as they come out of the common APIs, and guard an answer before a user sees it.

Supported shapes (no SDK needed, plain dicts or SDK objects with the same attributes):
  Anthropic Messages: assistant content blocks of type "tool_use", user blocks of type "tool_result"
  OpenAI Chat:        assistant messages with "tool_calls", then {"role": "tool", "content": ...}
  LangChain/LangGraph: messages with .type == "tool" / "ai" (ToolMessage, AIMessage)
"""
from __future__ import annotations

from .core import Report, check


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text_of(_get(b, "text", "")) if _get(b, "type") == "text" else
                         (b if isinstance(b, str) else "") for b in content)
    return str(content or "")


def split_transcript(messages) -> tuple[str, list[tuple[str, object]]]:
    """Return (final answer text, [(tool name, tool output), ...]) for the last turn of a transcript."""
    names: dict[str, str] = {}
    outputs: list[tuple[str, object]] = []
    answer = ""
    for m in messages:
        role = _get(m, "role") or _get(m, "type")
        content = _get(m, "content")
        if role in ("assistant", "ai"):
            for call in _get(m, "tool_calls") or []:                       # OpenAI / LangChain
                fn = _get(call, "function") or call
                names[_get(call, "id", "")] = _get(fn, "name", "tool")
            if isinstance(content, list):                                  # Anthropic
                for b in content:
                    if _get(b, "type") == "tool_use":
                        names[_get(b, "id", "")] = _get(b, "name", "tool")
            text = _text_of(content)
            if text.strip():
                answer = text
        elif role == "tool":
            cid = _get(m, "tool_call_id", "")
            outputs.append((names.get(cid) or _get(m, "name") or "tool", content))
        elif role in ("user", "human") and isinstance(content, list):
            for b in content:
                if _get(b, "type") == "tool_result":
                    raw = _get(b, "content")
                    outputs.append((names.get(_get(b, "tool_use_id", ""), "tool"), _text_of(raw) if isinstance(raw, list) else raw))
    return answer, outputs


def check_transcript(messages, **kw) -> Report:
    answer, outputs = split_transcript(messages)
    return check(answer, outputs, **kw)


class UnverifiedNumbers(ValueError):
    def __init__(self, report: Report):
        super().__init__("numbers without a receipt:\n" + report.to_text())
        self.report = report


def guard(answer: str, tool_outputs, on_fail: str = "raise", strict: bool = False):
    """Use right before an answer leaves your system.
    on_fail="raise"    raise UnverifiedNumbers (fail the request or the CI test)
    on_fail="redact"   replace numbers without a receipt with [unverified]
    on_fail="annotate" mark them inline, for review queues
    """
    report = check(answer, tool_outputs)
    if report.passed(strict=strict):
        return answer
    if on_fail == "redact":
        return report.redact()
    if on_fail == "annotate":
        return report.annotate()
    raise UnverifiedNumbers(report)


def langgraph_node(state: dict, on_fail: str = "annotate") -> dict:
    """Drop-in LangGraph node: checks the last AI message against the tool messages in this turn and adds the
    report to state["receipts"]. Wire it right before END."""
    messages = state.get("messages", [])
    report = check_transcript(messages)
    update = {"receipts": report.to_dict()}
    if not report.passed() and on_fail in ("annotate", "redact") and messages:
        last = messages[-1]
        text = report.annotate() if on_fail == "annotate" else report.redact()
        if isinstance(last, dict):
            update["messages"] = messages[:-1] + [{**last, "content": text}]
    return update
