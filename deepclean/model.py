"""Vendor-neutral internal representation of an AI coding session.

Claude Code JSONL is an input format, not Deep Clean's domain model. Keeping a
small normalized model here lets analysis evolve without coupling every
detector to Anthropic's private session schema.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from deepclean.turns import Turn, message_text


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: Any = None


@dataclass(frozen=True)
class ToolResult:
    tool_use_id: str
    content: Any
    char_count: int
    digest: str


@dataclass(frozen=True)
class NormalizedTurn:
    number: int
    start: int
    end: int
    preview: str
    message_count: int
    user_text: str
    assistant_text: str
    tool_uses: tuple[ToolUse, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()
    char_count: int = 0
    timestamp: str | None = None

    @property
    def has_tool_activity(self) -> bool:
        return bool(self.tool_uses or self.tool_results)


@dataclass(frozen=True)
class NormalizedSession:
    turns: tuple[NormalizedTurn, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def turn(self, number: int) -> NormalizedTurn:
        for turn in self.turns:
            if turn.number == number:
                return turn
        raise KeyError(number)


def _blocks(entry):
    content = entry.get("message", {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _stable_payload(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def normalize(entries, turns: list[Turn] | tuple[Turn, ...]) -> NormalizedSession:
    """Convert parsed vendor entries into Deep Clean's internal representation."""
    normalized = []

    for turn in turns:
        segment = entries[turn.start : turn.end]
        user_text = message_text(entries[turn.start]).strip()
        assistant_text = " ".join(
            message_text(entry)
            for entry in segment
            if entry.get("type") == "assistant"
        ).strip()

        tool_uses = []
        tool_results = []
        for entry in segment:
            for block in _blocks(entry):
                if block.get("type") == "tool_use" and block.get("id"):
                    tool_uses.append(
                        ToolUse(
                            id=str(block["id"]),
                            name=str(block.get("name", "")),
                            input=block.get("input"),
                        )
                    )
                elif block.get("type") == "tool_result" and block.get("tool_use_id"):
                    payload = block.get("content")
                    raw = _stable_payload(payload)
                    tool_results.append(
                        ToolResult(
                            tool_use_id=str(block["tool_use_id"]),
                            content=payload,
                            char_count=len(raw),
                            digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                        )
                    )

        timestamp = next(
            (entry.get("timestamp") for entry in segment if isinstance(entry.get("timestamp"), str)),
            None,
        )

        char_count = sum(
            len(json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str))
            for entry in segment
        )

        normalized.append(
            NormalizedTurn(
                number=turn.number,
                start=turn.start,
                end=turn.end,
                preview=turn.preview,
                message_count=turn.message_count,
                user_text=user_text,
                assistant_text=assistant_text,
                tool_uses=tuple(tool_uses),
                tool_results=tuple(tool_results),
                char_count=char_count,
                timestamp=timestamp,
            )
        )

    return NormalizedSession(turns=tuple(normalized))
