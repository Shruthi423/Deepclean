"""Splitting Claude Code sessions into active, archivable turns.

A turn starts when the human types a message and includes the active-branch
conversation records that follow until the next human message. Synthetic
slash-command/system records do not become turns. If the session has branched,
only the path that ends at the current leaf is considered active.
"""

from dataclasses import dataclass

PREVIEW_CHARS = 60

_SYNTHETIC_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<system-reminder>",
)

_COMPACT_SUMMARY_PREFIXES = (
    "this session is being continued from a previous conversation that ran out of context",
    "this session is being continued from a previous conversation that was compacted",
)


@dataclass
class Turn:
    number: int
    start: int
    end: int
    preview: str
    message_count: int
    indices: tuple[int, ...] = ()
    archivable: bool = True
    protected_reason: str | None = None


def turn_indices(turn):
    """Return the exact record indexes that belong to a turn."""
    return turn.indices or tuple(range(turn.start, turn.end))


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


def is_synthetic_user_entry(entry):
    """True for Claude-generated user-role records that are not human prompts."""
    if entry.get("type") != "user":
        return False
    if entry.get("isSidechain") or entry.get("isMeta"):
        return True
    text = message_text(entry).lstrip().casefold()
    return any(text.startswith(prefix) for prefix in _SYNTHETIC_PREFIXES)


def is_compact_summary(entry):
    """Recognize the user-role summary Claude Code injects after compaction."""
    if entry.get("type") != "user":
        return False
    message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    if entry.get("isCompactSummary") or entry.get("compactSummary"):
        return True
    if message.get("isCompactSummary") or message.get("compactSummary"):
        return True
    text = " ".join(message_text(entry).split()).casefold()
    return any(text.startswith(prefix) for prefix in _COMPACT_SUMMARY_PREFIXES)


def is_turn_start(entry):
    """True only for a human user message or a compact-summary pseudo-turn."""
    if entry.get("type") != "user" or entry.get("isSidechain"):
        return False
    if is_compact_summary(entry):
        return True
    if is_synthetic_user_entry(entry):
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


def _active_conversation_indices(entries):
    """Return conversation record indexes on the current Claude branch.

    Linear transcripts keep their historical behavior. When sibling records
    reveal a rewind/edit branch, Deep Clean follows parentUuid from the newest
    conversation leaf and ignores abandoned siblings.
    """
    conversation = [
        i for i, entry in enumerate(entries)
        if entry.get("type") in {"user", "assistant"} and not entry.get("isSidechain")
    ]
    if not conversation:
        return []

    by_uuid = {
        entry.get("uuid"): i
        for i, entry in enumerate(entries)
        if isinstance(entry.get("uuid"), str) and entry.get("uuid")
    }
    children = {}
    for i in conversation:
        parent = entries[i].get("parentUuid")
        if isinstance(parent, str) and parent:
            children.setdefault(parent, []).append(i)

    if not any(len(items) > 1 for items in children.values()):
        return conversation

    leaf_index = conversation[-1]
    leaf_uuid = entries[leaf_index].get("uuid")
    if not isinstance(leaf_uuid, str) or not leaf_uuid:
        return conversation

    active_uuids = set()
    current = leaf_uuid
    seen = set()
    while isinstance(current, str) and current and current not in seen:
        seen.add(current)
        active_uuids.add(current)
        index = by_uuid.get(current)
        if index is None:
            break
        parent = entries[index].get("parentUuid")
        if not isinstance(parent, str) or not parent:
            break
        current = parent

    active = [i for i in conversation if entries[i].get("uuid") in active_uuids]
    return active or conversation


def _apply_compaction_boundary(entries, active_indices):
    """Keep only records Claude can still see after the latest compaction."""
    compact_user_indexes = [i for i in active_indices if is_compact_summary(entries[i])]
    summary_record_indexes = [
        i for i, entry in enumerate(entries)
        if entry.get("type") == "summary"
    ]

    boundary = None
    inclusive = False
    if compact_user_indexes:
        boundary = compact_user_indexes[-1]
        inclusive = True
    if summary_record_indexes and (boundary is None or summary_record_indexes[-1] > boundary):
        boundary = summary_record_indexes[-1]
        inclusive = False

    if boundary is None:
        return active_indices
    if inclusive:
        return [i for i in active_indices if i >= boundary]
    return [i for i in active_indices if i > boundary]


def active_conversation_indices(entries):
    """Exact conversation indexes on the branch/context Claude can currently see."""
    return _apply_compaction_boundary(entries, _active_conversation_indices(entries))


def split_turns(entries):
    """Return active-context turns in order.

    Abandoned branches and pre-compaction history are omitted. Compact summaries
    remain visible but are marked unarchivable.
    """
    active = active_conversation_indices(entries)
    start_positions = [pos for pos, i in enumerate(active) if is_turn_start(entries[i])]
    turns = []

    for k, start_pos in enumerate(start_positions):
        stop_pos = start_positions[k + 1] if k + 1 < len(start_positions) else len(active)
        indices = tuple(active[start_pos:stop_pos])
        if not indices:
            continue
        start = indices[0]
        count = sum(
            1
            for i in indices
            if entries[i].get("type") == "assistant"
            or (entries[i].get("type") == "user" and not is_synthetic_user_entry(entries[i]))
        )
        compact = is_compact_summary(entries[start])
        turns.append(
            Turn(
                number=len(turns) + 1,
                start=start,
                end=indices[-1] + 1,
                preview=preview(message_text(entries[start])),
                message_count=count,
                indices=indices,
                archivable=not compact,
                protected_reason="compact summary" if compact else None,
            )
        )
    return turns
