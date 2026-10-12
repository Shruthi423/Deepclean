"""Build a safe cleaned copy of a Claude Code session."""

import copy
import uuid

from deepclean.turns import (
    active_conversation_indices,
    is_synthetic_user_entry,
    is_turn_start,
    preview,
    turn_indices,
)

REMOVABLE_TYPES = {"user", "assistant"}
REFERENCE_FIELDS = ("parentUuid", "leafUuid", "logicalParentUuid", "messageId")


class CleanError(Exception):
    """The requested clean is not allowed or would produce a broken session."""


def build_stub(archived_turns):
    starts = "; ".join(f'"{t.preview}"' for t in archived_turns)
    count = len(archived_turns)
    noun = "exchange" if count == 1 else "exchanges"
    return (
        f"[Deep Clean note: the user archived {count} earlier {noun} to keep this "
        f"session focused. They began with: {starts}. If you need details from "
        f"them, ask the user.]"
    )


def _check_choices(turns, archive_numbers, protect_last):
    if protect_last < 1:
        raise CleanError("At least the last turn must be protected.")
    if not archive_numbers:
        raise CleanError("No turns were chosen for archiving.")
    valid = {t.number for t in turns}
    protected = {t.number for t in turns[-protect_last:]}
    structurally_protected = {t.number for t in turns if not t.archivable}
    for number in archive_numbers:
        if number not in valid:
            raise CleanError(f"Turn {number} does not exist.")
        if number in structurally_protected:
            turn = next(t for t in turns if t.number == number)
            reason = turn.protected_reason or "session structure"
            raise CleanError(f"Turn {number} is protected ({reason}).")
        if number in protected:
            raise CleanError(f"Turn {number} is one of the last {protect_last} and is protected.")


def _runs(numbers):
    runs = []
    for n in sorted(numbers):
        if runs and n == runs[-1][-1] + 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    return runs


def _prepend_text(entry, text):
    message = entry["message"]
    content = message.get("content")
    if isinstance(content, str):
        message["content"] = f"{text}\n\n{content}"
    elif isinstance(content, list):
        message["content"] = [{"type": "text", "text": text}] + content
    else:
        raise CleanError("Could not attach the stub note to the next message.")


def check_tool_pairs(entries):
    """Validate tool call/result integrity on the active conversation branch.

    This intentionally validates raw active conversation records rather than
    only successfully parsed turns. That way malformed orphan calls/results
    are still caught instead of disappearing from the validator.
    """
    active_indexes = set(active_conversation_indices(entries))
    open_calls = {}
    seen_calls = set()
    current_turn = 0

    for index, entry in enumerate(entries):
        if index not in active_indexes:
            continue

        if entry.get("type") == "user" and is_turn_start(entry):
            current_turn += 1
            if open_calls:
                call_id, source_turn = next(iter(open_calls.items()))
                raise CleanError(
                    f"Tool call {call_id!r} in turn {source_turn or '?'} has no result "
                    f"before turn {current_turn}."
                )

        content = entry.get("message", {}).get("content") if entry.get("type") in REMOVABLE_TYPES else None
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []

        for block in blocks:
            if block.get("type") == "tool_use" and block.get("id"):
                call_id = str(block["id"])
                open_calls[call_id] = current_turn or 1
                seen_calls.add(call_id)
            elif block.get("type") == "tool_result":
                call_id = block.get("tool_use_id")
                call_id = str(call_id) if call_id is not None else ""
                if not call_id or call_id not in seen_calls:
                    raise CleanError(
                        f"Tool result {call_id or '<missing id>'!r} in turn "
                        f"{current_turn or 1} has no matching call."
                    )
                open_calls.pop(call_id, None)

    if open_calls:
        call_id, source_turn = next(iter(open_calls.items()))
        raise CleanError(f"Tool call {call_id!r} in turn {source_turn or 1} has no result.")

def clean(entries, turns, archive_numbers, protect_last, new_session_id=None):
    """Return (cleaned_entries, new_session_id). The input list is not modified."""
    _check_choices(turns, archive_numbers, protect_last)
    new_session_id = new_session_id or str(uuid.uuid4())
    by_number = {t.number: t for t in turns}

    remove = set()
    for number in archive_numbers:
        turn = by_number[number]
        for i in turn_indices(turn):
            entry = entries[i]
            if entry.get("type") not in REMOVABLE_TYPES:
                continue
            if is_synthetic_user_entry(entry):
                continue
            remove.add(i)

    removed_ids = {entries[i]["uuid"] for i in remove if entries[i].get("uuid")}

    stubs = {}
    for run in _runs(archive_numbers):
        next_turn = by_number.get(run[-1] + 1)
        if next_turn is None:
            raise CleanError("Cleaning would archive the final active turn.")
        stubs[next_turn.start] = build_stub([by_number[n] for n in run])

    parent_of = {e["uuid"]: e.get("parentUuid") for e in entries if e.get("uuid")}

    def nearest_kept(line_id):
        seen = set()
        while line_id in removed_ids:
            if line_id in seen:
                raise CleanError("The session's message chain has a loop.")
            seen.add(line_id)
            line_id = parent_of.get(line_id)
        return line_id

    new_ids = {
        e["uuid"]: str(uuid.uuid4())
        for i, e in enumerate(entries)
        if e.get("uuid") and i not in remove
    }

    cleaned = []
    for i, original in enumerate(entries):
        if i in remove:
            continue
        entry = copy.deepcopy(original)
        if entry.get("uuid"):
            entry["uuid"] = new_ids[entry["uuid"]]
        for field in REFERENCE_FIELDS:
            value = entry.get(field)
            if isinstance(value, str):
                value = nearest_kept(value)
                entry[field] = new_ids.get(value, value)
        if "sessionId" in entry:
            entry["sessionId"] = new_session_id
        if i in stubs:
            _prepend_text(entry, stubs[i])
        cleaned.append(entry)

    check_tool_pairs(cleaned)
    return cleaned, new_session_id


def archived_previews(turns, archive_numbers):
    by_number = {t.number: t for t in turns}
    return [preview(by_number[n].preview) for n in sorted(archive_numbers)]
