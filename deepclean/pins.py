"""Project-level source-of-truth pins for Deep Clean."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PINS_FILE = Path.home() / ".deepclean" / "pins.json"


class PinsError(Exception):
    """Pins storage is missing expected structure or cannot be read safely."""


def _project_id(project):
    raw = str(project or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _empty():
    return {"projects": {}}


def _validate(data):
    if not isinstance(data, dict):
        raise PinsError("pins.json must contain a JSON object.")
    projects = data.get("projects")
    if not isinstance(projects, dict):
        raise PinsError("pins.json has no valid 'projects' object.")

    for key, record in projects.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise PinsError("pins.json contains an invalid project record.")
        pins = record.get("pins", [])
        if not isinstance(pins, list):
            raise PinsError("pins.json contains an invalid pins list.")
        for item in pins:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise PinsError("pins.json contains an invalid pin entry.")
    return data


def _load(path=PINS_FILE):
    path = Path(path)
    if not path.exists():
        return _empty()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise PinsError(f"Could not read {path}: {err}") from err

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        raise PinsError(
            f"{path} is corrupt JSON. Nothing was changed; repair or restore the file before using pins."
        ) from err
    return _validate(data)


def _save(data, path=PINS_FILE):
    _validate(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def list_pins(project, path=PINS_FILE):
    data = _load(path)
    record = data.get("projects", {}).get(_project_id(project), {})
    return list(record.get("pins", []))


def pin(project, text, source_turn=None, path=PINS_FILE):
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("Cannot pin empty text.")

    data = _load(path)
    projects = data.setdefault("projects", {})
    key = _project_id(project)
    record = projects.setdefault(key, {"project": str(project), "pins": []})

    if any(item.get("text") == text for item in record["pins"]):
        return False

    record["pins"].append(
        {
            "text": text,
            "source_turn": source_turn,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save(data, path)
    return True


def unpin(project, index, path=PINS_FILE):
    data = _load(path)
    record = data.get("projects", {}).get(_project_id(project))
    if not record:
        return False
    pins = record.get("pins", [])
    if index < 1 or index > len(pins):
        return False
    pins.pop(index - 1)
    _save(data, path)
    return True


def protected_turn_numbers(normalized_session, project, path=PINS_FILE):
    items = list_pins(project, path)
    pinned_texts = {item.get("text", "") for item in items}
    source_turns = {
        item.get("source_turn")
        for item in items
        if isinstance(item.get("source_turn"), int)
    }
    return {
        turn.number
        for turn in normalized_session.turns
        if turn.number in source_turns
        or " ".join(turn.user_text.split()) in pinned_texts
    }
