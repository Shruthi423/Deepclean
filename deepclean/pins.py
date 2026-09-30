"""Project-level source-of-truth pins for Deep Clean."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PINS_FILE = Path.home() / ".deepclean" / "pins.json"


def _project_id(project):
    raw = str(project or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _load(path=PINS_FILE):
    path = Path(path)
    if not path.exists():
        return {"projects": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"projects": {}}
    return data if isinstance(data, dict) else {"projects": {}}


def _save(data, path=PINS_FILE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    pinned_texts = {item.get("text", "") for item in list_pins(project, path)}
    return {
        turn.number
        for turn in normalized_session.turns
        if " ".join(turn.user_text.split()) in pinned_texts
    }
