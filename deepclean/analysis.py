"""Deterministic, advisory context analysis for Deep Clean.

This module never changes a session. It surfaces review signals that help a
person decide what may no longer deserve active context.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from deepclean.context_graph import build_context_graph
from deepclean.findings import Finding
from deepclean.model import NormalizedSession, normalize

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

CORRECTION_MARKERS = (
    "i already said",
    "i told you",
    "again",
    "for the third time",
    "no, i meant",
    "that's not what i meant",
    "that is not what i meant",
)


def _normalize(text: str) -> str:
    text = text.casefold().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def detect_lightweight_acknowledgements(session: NormalizedSession):
    """Find tiny courtesy exchanges, never bare yes/no decisions."""
    findings = []
    for turn in session.turns:
        user_text = _normalize(turn.user_text)
        if user_text not in ACKNOWLEDGEMENTS:
            continue
        if turn.has_tool_activity:
            continue
        if len(turn.assistant_text) > 240:
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


def detect_repeated_user_text(session: NormalizedSession):
    """Find exact repeated substantive prompts, a cheap signal of re-explanation."""
    groups = {}
    for turn in session.turns:
        text = _normalize(turn.user_text)
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


def detect_near_duplicate_user_text(session: NormalizedSession, threshold=0.88):
    """Find highly similar substantive prompts without claiming semantic equivalence."""
    candidates = []
    for turn in session.turns:
        text = _normalize(turn.user_text)
        if len(text) >= 40:
            candidates.append((turn.number, text))

    findings = []
    seen_pairs = set()
    for i, (left_number, left_text) in enumerate(candidates):
        for right_number, right_text in candidates[i + 1:]:
            if left_text == right_text:
                continue
            score = SequenceMatcher(None, left_text, right_text).ratio()
            if score < threshold:
                continue
            pair = (left_number, right_number)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            findings.append(
                Finding(
                    kind="near_duplicate_user_text",
                    turns=pair,
                    title="Possible re-explanation",
                    detail=f"These user messages are very similar ({score:.0%} textual similarity). Review whether they repeat the same requirement.",
                    confidence=0.80,
                    mechanical=False,
                )
            )
    return findings


def detect_correction_markers(session: NormalizedSession):
    """Find explicit language that often signals context loss or correction loops."""
    findings = []
    for turn in session.turns:
        text = _normalize(turn.user_text)
        matched = next((marker for marker in CORRECTION_MARKERS if marker in text), None)
        if not matched:
            continue
        findings.append(
            Finding(
                kind="correction_marker",
                turns=(turn.number,),
                title="Possible correction loop",
                detail=f'The user used "{matched}", which can indicate the model lost or distorted earlier context.',
                confidence=0.85,
                mechanical=False,
            )
        )
    return findings


def detect_large_tool_results(session: NormalizedSession, threshold=4000):
    """Find turns dominated by large tool-result payloads."""
    findings = []
    for turn in session.turns:
        size = sum(result.char_count for result in turn.tool_results)
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


def detect_duplicate_tool_results(session: NormalizedSession, min_size=200):
    """Find identical non-trivial tool results repeated across different turns."""
    seen = {}
    groups = {}
    for turn in session.turns:
        for result in turn.tool_results:
            if result.char_count < min_size:
                continue
            if result.digest in seen:
                groups.setdefault(result.digest, {seen[result.digest]}).add(turn.number)
            else:
                seen[result.digest] = turn.number

    findings = []
    for numbers in groups.values():
        findings.append(
            Finding(
                kind="duplicate_tool_output",
                turns=tuple(sorted(numbers)),
                title="Duplicate tool output",
                detail="Identical non-trivial tool-result content appears in multiple turns.",
                confidence=1.0,
            )
        )
    return findings


def analyze(entries, turns):
    """Run conservative detectors over Deep Clean's normalized session model."""
    session = normalize(entries, turns)
    build_context_graph(session)  # Build once now; semantic relations can extend it later.

    detectors = (
        detect_lightweight_acknowledgements,
        detect_repeated_user_text,
        detect_near_duplicate_user_text,
        detect_correction_markers,
        detect_large_tool_results,
        detect_duplicate_tool_results,
    )

    findings = []
    for detector in detectors:
        findings.extend(detector(session))

    return sorted(findings, key=lambda f: (min(f.turns), f.kind))
