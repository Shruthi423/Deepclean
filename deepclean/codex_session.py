"""Read, analyze, and safely copy Codex CLI rollout sessions.

Codex rollouts are append-only JSONL under ~/.codex/sessions/YYYY/MM/DD/.
Deep Clean only writes a NEW rollout with a fresh thread id. Unknown or
incomplete shapes fail closed.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from deepclean.model import NormalizedSession, NormalizedTurn, ToolResult, ToolUse
from deepclean.turns import Turn, preview

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
SESSIONS_DIR = CODEX_HOME / "sessions"

KNOWN_RECORD_TYPES = {
    "session_meta",
    "turn_context",
    "event_msg",
    "response_item",
    "compacted",
    "inter_agent_communication",
    "inter_agent_communication_metadata",
    "realtime_item",
}


class CodexFormatError(Exception):
    """The rollout does not match a Codex format Deep Clean understands."""


def load(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for number, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                raise CodexFormatError(f"Line {number} is not valid JSON.") from None
            if not isinstance(entry, dict):
                raise CodexFormatError(f"Line {number} is not a JSON object.")
            entries.append(entry)
    check_format(entries)
    return entries


def check_format(entries):
    if not entries or entries[0].get("type") != "session_meta":
        raise CodexFormatError("The rollout does not start with session_meta.")

    payload = entries[0].get("payload")
    if not isinstance(payload, dict):
        raise CodexFormatError("session_meta.payload is missing.")

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else payload
    if not isinstance(meta, dict) or not meta.get("id"):
        raise CodexFormatError("session_meta has no thread id.")

    unknown = sorted({e.get("type") for e in entries if e.get("type") not in KNOWN_RECORD_TYPES})
    if unknown:
        raise CodexFormatError(
            "Unknown Codex rollout record type(s): " + ", ".join(map(str, unknown))
        )

    if not any(_is_user_message(e) for e in entries):
        raise CodexFormatError("No user response_item messages found.")


def find_latest(sessions_dir=SESSIONS_DIR):
    root = Path(sessions_dir)
    if not root.exists():
        return None
    files = [p for p in root.rglob("*.jsonl") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _response_payload(entry):
    payload = entry.get("payload")
    return payload if isinstance(payload, dict) else {}


def _is_user_message(entry):
    payload = _response_payload(entry)
    return (
        entry.get("type") == "response_item"
        and payload.get("type") == "message"
        and payload.get("role") == "user"
    )


def _message_text(entry):
    payload = _response_payload(entry)
    if payload.get("type") != "message":
        return ""
    parts = []
    for block in payload.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") in {"input_text", "output_text", "text"}:
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return " ".join(parts).strip()


def split_turns(entries):
    """Split Codex rollout records into whole user turns."""
    user_indexes = [i for i, entry in enumerate(entries) if _is_user_message(entry)]
    turns = []

    for k, user_index in enumerate(user_indexes):
        lower_bound = user_indexes[k - 1] + 1 if k else 1
        start = user_index

        # Include the latest turn_context immediately preceding this user turn.
        for i in range(user_index - 1, lower_bound - 1, -1):
            if entries[i].get("type") == "turn_context":
                start = i
                break
            if _is_user_message(entries[i]):
                break

        next_user = user_indexes[k + 1] if k + 1 < len(user_indexes) else len(entries)
        end = next_user
        if k + 1 < len(user_indexes):
            # If the next user has a turn_context before it, that context belongs
            # to the next turn rather than this one.
            for i in range(next_user - 1, user_index, -1):
                if entries[i].get("type") == "turn_context":
                    end = i
                    break
                if _is_user_message(entries[i]):
                    break

        segment = entries[start:end]
        count = sum(
            1
            for e in segment
            if e.get("type") == "response_item"
            and _response_payload(e).get("type") == "message"
        )
        turns.append(
            Turn(
                number=k + 1,
                start=start,
                end=end,
                preview=preview(_message_text(entries[user_index])),
                message_count=count,
            )
        )
    return turns


def normalize(entries, turns):
    normalized = []
    for turn in turns:
        segment = entries[turn.start : turn.end]
        user_entry = next((e for e in segment if _is_user_message(e)), None)
        if user_entry is None:
            raise CodexFormatError(f"Turn {turn.number} has no user message.")

        assistant_texts = []
        tool_uses = []
        tool_results = []

        for entry in segment:
            if entry.get("type") != "response_item":
                continue
            payload = _response_payload(entry)
            kind = payload.get("type")

            if kind == "message" and payload.get("role") == "assistant":
                text = _message_text(entry)
                if text:
                    assistant_texts.append(text)
            elif kind in {"function_call", "custom_tool_call"}:
                call_id = payload.get("call_id") or payload.get("id")
                if call_id:
                    tool_uses.append(
                        ToolUse(
                            id=str(call_id),
                            name=str(payload.get("name") or kind),
                            input=payload.get("arguments") or payload.get("input"),
                        )
                    )
            elif kind in {"function_call_output", "custom_tool_call_output"}:
                call_id = payload.get("call_id") or payload.get("id")
                if call_id:
                    content = payload.get("output")
                    raw = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
                    import hashlib
                    tool_results.append(
                        ToolResult(
                            tool_use_id=str(call_id),
                            content=content,
                            char_count=len(raw),
                            digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                        )
                    )

        char_count = sum(
            len(json.dumps(e, ensure_ascii=False, sort_keys=True, default=str))
            for e in segment
        )
        timestamp = next(
            (e.get("timestamp") for e in segment if isinstance(e.get("timestamp"), str)),
            None,
        )

        normalized.append(
            NormalizedTurn(
                number=turn.number,
                start=turn.start,
                end=turn.end,
                preview=turn.preview,
                message_count=turn.message_count,
                user_text=_message_text(user_entry),
                assistant_text=" ".join(assistant_texts),
                tool_uses=tuple(tool_uses),
                tool_results=tuple(tool_results),
                char_count=char_count,
                timestamp=timestamp,
            )
        )

    return NormalizedSession(turns=tuple(normalized), metadata={"provider": "codex"})


def working_folder(entries):
    payload = entries[0].get("payload", {})
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else payload
    cwd = meta.get("cwd") if isinstance(meta, dict) else None
    return str(cwd) if cwd else None


def session_id(entries):
    payload = entries[0].get("payload", {})
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else payload
    value = meta.get("id") if isinstance(meta, dict) else None
    return str(value) if value else None


def _check_choices(turns, archive_numbers, protect_last, protected_numbers=None):
    if protect_last < 1:
        raise CodexFormatError("At least the last turn must be protected.")
    if not archive_numbers:
        raise CodexFormatError("No turns were chosen for archiving.")

    valid = {t.number for t in turns}
    protected = {t.number for t in turns[-protect_last:]}
    protected.update(protected_numbers or set())

    for number in archive_numbers:
        if number not in valid:
            raise CodexFormatError(f"Turn {number} does not exist.")
        if number in protected:
            raise CodexFormatError(f"Turn {number} is protected.")


def clean(entries, turns, archive_numbers, protect_last, protected_numbers=None, new_session_id=None):
    """Return a cleaned Codex rollout copy with a fresh thread id."""
    _check_choices(turns, archive_numbers, protect_last, protected_numbers)
    cleaned = copy.deepcopy(entries)
    remove = set()

    by_number = {t.number: t for t in turns}
    for number in archive_numbers:
        turn = by_number[number]
        remove.update(range(turn.start, turn.end))

    cleaned = [entry for i, entry in enumerate(cleaned) if i not in remove]
    if not cleaned or cleaned[0].get("type") != "session_meta":
        raise CodexFormatError("Cleaning would remove Codex session metadata.")

    new_id = new_session_id or str(uuid.uuid4())
    payload = cleaned[0].get("payload", {})
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else payload

    if not isinstance(meta, dict) or "id" not in meta:
        raise CodexFormatError("Could not update Codex session id safely.")

    meta["id"] = new_id
    if "session_id" in meta:
        meta["session_id"] = new_id
    if "timestamp" in meta:
        meta["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if any("ordinal" in e for e in cleaned):
        for ordinal, entry in enumerate(cleaned):
            entry["ordinal"] = ordinal

    check_format(cleaned)
    return cleaned, new_id


def write_new(entries, session_id_value, sessions_dir=SESSIONS_DIR):
    """Atomically write a new rollout in today's Codex session directory."""
    now = datetime.now()
    folder = Path(sessions_dir) / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    folder.mkdir(parents=True, exist_ok=True)

    stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    target = folder / f"rollout-{stamp}-{session_id_value}.jsonl"
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite {target}")

    fd, tmp_path = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(tmp_path, target)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    return target


def resume_command(session_id_value):
    return f"codex resume {session_id_value}"
