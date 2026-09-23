"""
Building a cleaned copy of a session.

Rules enforced here:
  1. Only turns the user chose are archived.
  2. The last few turns are protected and can never be archived.
  3. Whole turns are archived, so a tool call never loses its result.
  4. A short stub replaces each archived stretch, so Claude knows something
     was there.
  5. The copy gets a new session id and new line ids. The original file is
     never touched, which makes every clean reversible.
  6. Before anything is written, the copy is checked. If a check fails,
     nothing is written.
"""

import copy
import uuid

from deepclean.turns import message_text, preview

# Only conversation lines are removed. Other line types (snapshots, summaries,
# system notes) are kept, with their references updated.
REMOVABLE_TYPES = {"user", "assistant"}

# Fields that point at another line's uuid.
REFERENCE_FIELDS = ("parentUuid", "leafUuid", "logicalParentUuid", "messageId")


class CleanError(Exception):
    """The requested clean is not allowed or would produce a broken session."""


def build_stub(archived_turns):
    """The note Claude sees in place of archived turns."""
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
    for number in archive_numbers:
        if number not in valid:
            raise CleanError(f"Turn {number} does not exist.")
        if number in protected:
            raise CleanError(f"Turn {number} is one of the last {protect_last} and is protected.")


def _runs(numbers):
    """Group sorted numbers into consecutive runs: [2,3,5] -> [[2,3],[5]]."""
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
    """
    Every tool result must follow its tool call, and every tool call must get
    a result before the user's next message. Otherwise Claude would reject
    the session.
    """
    from deepclean.turns import is_turn_start

    open_calls = set()
    seen_calls = set()
    for entry in entries:
        content = entry.get("message", {}).get("content") if entry.get("type") in REMOVABLE_TYPES else None
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []

        if entry.get("type") == "user" and is_turn_start(entry) and open_calls:
            raise CleanError("A tool call would be left without its result.")

        for block in blocks:
            if block.get("type") == "tool_use" and block.get("id"):
                open_calls.add(block["id"])
                seen_calls.add(block["id"])
            elif block.get("type") == "tool_result":
                call_id = block.get("tool_use_id")
                if call_id not in seen_calls:
                    raise CleanError("A tool result would be left without its tool call.")
                open_calls.discard(call_id)


def clean(entries, turns, archive_numbers, protect_last, new_session_id=None):
    """
    Return (cleaned_entries, new_session_id). The input list is not modified.
    """
    _check_choices(turns, archive_numbers, protect_last)
    new_session_id = new_session_id or str(uuid.uuid4())
    by_number = {t.number: t for t in turns}

    # Which lines go.
    remove = set()
    for number in archive_numbers:
        turn = by_number[number]
        for i in range(turn.start, turn.end):
            if entries[i].get("type") in REMOVABLE_TYPES:
                remove.add(i)
    removed_ids = {entries[i]["uuid"] for i in remove if entries[i].get("uuid")}

    # Where each stub goes: the first line of the turn right after each run.
    stubs = {}
    for run in _runs(archive_numbers):
        next_turn = by_number[run[-1] + 1]  # exists, because the last turn is protected
        stubs[next_turn.start] = build_stub([by_number[n] for n in run])

    # A removed line's children must attach to its nearest kept ancestor.
    parent_of = {e["uuid"]: e.get("parentUuid") for e in entries if e.get("uuid")}

    def nearest_kept(line_id):
        seen = set()
        while line_id in removed_ids:
            if line_id in seen:
                raise CleanError("The session's message chain has a loop.")
            seen.add(line_id)
            line_id = parent_of.get(line_id)
        return line_id

    # Fresh ids for the copy, so it never collides with the original.
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
