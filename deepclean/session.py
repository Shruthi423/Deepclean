"""
Reading and writing Claude Code session files.

A session file is a .jsonl file: one JSON object per line. Claude Code keeps
them under ~/.claude/projects/<project-folder>/<session-id>.jsonl.

The format is not officially documented, so this module checks that a file
looks the way we expect before anything else touches it. If the check fails,
Deep Clean stops and changes nothing.
"""

import json
import os
import tempfile
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Line types that hold the actual conversation.
CONVERSATION_TYPES = {"user", "assistant"}


class SessionFormatError(Exception):
    """The file does not look like a Claude Code session we understand."""


def load(path):
    """Read a session file and return its lines as a list of dicts."""
    entries = []
    with open(path, encoding="utf-8") as f:
        for number, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                raise SessionFormatError(f"Line {number} is not valid JSON.") from None
            if not isinstance(entry, dict):
                raise SessionFormatError(f"Line {number} is not a JSON object.")
            entries.append(entry)
    check_format(entries)
    return entries


def check_format(entries):
    """Stop early if the file does not match the format this version expects."""
    conversation = [e for e in entries if e.get("type") in CONVERSATION_TYPES]
    if not conversation:
        raise SessionFormatError("No user or assistant messages found.")
    for entry in conversation:
        if not entry.get("uuid"):
            raise SessionFormatError(
                "A message line has no 'uuid'. The session format may have changed."
            )
        message = entry.get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise SessionFormatError(
                "A message line has no 'message.content'. The session format may have changed."
            )


def find_latest(projects_dir=PROJECTS_DIR):
    """Return the most recently changed session file, or None."""
    projects_dir = Path(projects_dir)
    if not projects_dir.exists():
        return None
    files = [p for p in projects_dir.glob("*/*.jsonl") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def working_folder(entries):
    """The folder the session was started in, if the file records it."""
    for entry in entries:
        if entry.get("cwd"):
            return entry["cwd"]
    return None


def write_new(entries, folder, session_id):
    """
    Write entries to a NEW file named <session_id>.jsonl in folder.

    Never overwrites an existing file. Writes to a temporary file first and
    then renames it, so a crash can never leave a half-written session.
    """
    folder = Path(folder)
    target = folder / f"{session_id}.jsonl"
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
