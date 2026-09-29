"""Deterministic, advisory context analysis for Deep Clean.

This module never changes a session. It surfaces review signals that help a
person decide what may no longer deserve active context.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from deepclean.turns import Turn, message_text


@dataclass(frozen=True)
class Finding:
    """One reason a turn or group of turns deserves human review."""

    kind: str
    turns: tuple[int, ...]
    title: str
    detail: str
    confidence: float
    suggested_action: str = "review"
    mechanical: bool = True


ACKNOWLEDGEMENTS = {
    "thanks",
    "thank you",
    "thanks!",
    "thank you!",
    "ok",
    "okay",
    "got it",
    "got it!",
    "sounds good",
    "perfect",
}


def _normalize(text: str) -> str:
    text = text.casefold().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _blocks(entry):
    content = entry.get("message", {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _turn_entries(entries, turn: Turn):
    return entries[turn.start : turn.end]


def _assistant_text(entries, turn: Turn) -> str:
    return " ".join(
        message_text(entry)
        for entry in _turn_entries(entries, turn)
        if entry.get("type") == "assistant"
    ).strip()


def _has_tool_activity(entries, turn: Turn) -> bool:
    for entry in _turn_entries(entries, turn):
        for block in _blocks(entry):
            if block.get("type") in {"tool_use", "tool_result"}:
                return True
    return False


def _tool_result_payloads(entries, turn: Turn):
    for entry in _turn_entries(entries, turn):
        for block in _blocks(entry):
            if block.get("type") == "tool_result":
                yield block.get("content")


def detect_lightweight_acknowledgements(entries, turns: Iterable[Turn]):
    """Find tiny courtesy exchanges, never bare yes/no decisions."""
    findings = []
    for turn in turns:
        user_text = _normalize(message_text(entries[turn.start]))
        if user_text not in ACKNOWLEDGEMENTS:
            continue
        if _has_tool_activity(entries, turn):
            continue
        assistant_text = _assistant_text(entries, turn)
        if len(assistant_text) > 240:
            continue
        findings.append(
            Finding(
                kind="lightweight_acknowledgement",
                turns=(turn.number,),
                title="Lightweight acknowledgement exchange",
                detail="The user acknowledgement and assistant reply are both short and contain no tool activity.",
                confidence=0.98,
            )
        )
    return findings


def detect_repeated_user_text(entries, turns: Iterable[Turn]):
    """Find exact repeated substantive prompts, a cheap signal of re-explanation."""
    groups = {}
    for turn in turns:
        text = _normalize(message_text(entries[turn.start]))
        if len(text) < 24:
            continue
        groups.setdefault(text, []).append(turn.number)

    findings = []
    for numbers in groups.values():
        if len(numbers) < 2:
            continue
        findings.append(
            Finding(
                kind="repeated_user_text",
                turns=tuple(numbers),
                title="Repeated user requirement",
                detail="The same substantive user text appears in multiple turns. This may indicate re-explanation or a source-of-truth problem.",
                confidence=0.95,
            )
        )
    return findings


def detect_large_tool_results(entries, turns: Iterable[Turn], threshold=4000):
    """Find turns dominated by large tool-result payloads."""
    findings = []
    for turn in turns:
        size = 0
        for payload in _tool_result_payloads(entries, turn):
            size += len(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        if size < threshold:
            continue
        findings.append(
            Finding(
                kind="large_tool_output",
                turns=(turn.number,),
                title="Large tool output",
                detail=f"Tool results in this turn contain about {size:,} characters. Review whether the output is still useful.",
                confidence=0.99,
            )
        )
    return findings


def detect_duplicate_tool_results(entries, turns: Iterable[Turn], min_size=200):
    """Find identical non-trivial tool results repeated across different turns."""
    seen = {}
    groups = {}
    for turn in turns:
        for payload in _tool_result_payloads(entries, turn):
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if len(raw) < min_size:
                continue
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if digest in seen:
                groups.setdefault(digest, {seen[digest]}).add(turn.number)
            else:
                seen[digest] = turn.number

    findings = []
    for numbers in groups.values():
        ordered = tuple(sorted(numbers))
        findings.append(
            Finding(
                kind="duplicate_tool_output",
                turns=ordered,
                title="Duplicate tool output",
                detail="Identical non-trivial tool-result content appears in multiple turns.",
                confidence=1.0,
            )
        )
    return findings


def analyze(entries, turns):
    """Run cheap deterministic detectors. No session content is modified."""
    detectors = (
        detect_lightweight_acknowledgements,
        detect_repeated_user_text,
        detect_large_tool_results,
        detect_duplicate_tool_results,
    )
    findings = []
    for detector in detectors:
        findings.extend(detector(entries, turns))
    return sorted(findings, key=lambda f: (min(f.turns), f.kind))
