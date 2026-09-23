"""
Splitting a session into turns.

A turn starts when you type a message, and includes everything that follows
until your next message: Claude's replies, its tool calls, and their results.
Because a tool call and its result always sit inside the same turn, archiving
whole turns can never separate them.
"""

from dataclasses import dataclass

PREVIEW_CHARS = 60


@dataclass
class Turn:
    number: int          # 1-based, as shown to the user
    start: int           # index of the first line of this turn
    end: int             # index just after the last line of this turn
    preview: str         # first words of what the user typed
    message_count: int   # user and assistant lines in this turn


def message_text(entry):
    """Plain text of a message, ignoring tool calls and tool results."""
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def is_turn_start(entry):
    """True if this line is something the user typed (not a tool result)."""
    if entry.get("type") != "user" or entry.get("isSidechain") or entry.get("isMeta"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        has_text = any(b.get("type") == "text" for b in blocks)
        has_tool_result = any(b.get("type") == "tool_result" for b in blocks)
        return has_text and not has_tool_result
    return False


def preview(text, limit=PREVIEW_CHARS):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def split_turns(entries):
    """Return the session's turns in order. Lines before the first turn belong to none."""
    starts = [i for i, e in enumerate(entries) if is_turn_start(e)]
    turns = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(entries)
        count = sum(
            1 for e in entries[start:end] if e.get("type") in ("user", "assistant")
        )
        turns.append(
            Turn(
                number=k + 1,
                start=start,
                end=end,
                preview=preview(message_text(entries[start])),
                message_count=count,
            )
        )
    return turns
