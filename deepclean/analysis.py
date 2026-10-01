"""Advisory context analysis for Deep Clean.

Analysis never changes a session. Deterministic checks run first. Higher-level
signals are deliberately conservative and always require human review.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from deepclean.context_graph import build_context_graph
from deepclean.findings import Finding
from deepclean.model import NormalizedSession, normalize

ACKNOWLEDGEMENTS = {
    "thanks", "thank you", "thanks!", "thank you!", "ok", "okay",
    "got it", "got it!", "sounds good", "perfect",
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

SUPERSESSION_MARKERS = (
    "instead",
    "replace ",
    "switch to ",
    "switch from ",
    "now use ",
    "change ",
    "use this instead",
    "no longer ",
)

NEGATIVE_MARKERS = (
    " don't ",
    " do not ",
    " shouldn't ",
    " should not ",
    " never ",
    " not ",
    " remove ",
    " avoid ",
    " disable ",
)

POSITIVE_MARKERS = (
    " keep ",
    " use ",
    " should ",
    " enable ",
    " retain ",
    " include ",
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "at",
    "with", "this", "that", "it", "is", "are", "be", "as", "i", "we", "you",
    "my", "our", "your", "please", "now", "just", "still", "make",
}


def _normalize(text: str) -> str:
    text = text.casefold().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_./-]{2,}", _normalize(text))
        if token not in STOPWORDS
    }


def _topic_similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _polarity(text: str) -> int:
    wrapped = f" {_normalize(text)} "
    negative = any(marker in wrapped for marker in NEGATIVE_MARKERS)
    positive = any(marker in wrapped for marker in POSITIVE_MARKERS)
    if negative:
        return -1
    if positive:
        return 1
    return 0


def detect_lightweight_acknowledgements(session: NormalizedSession):
    findings = []
    for turn in session.turns:
        user_text = _normalize(turn.user_text)
        if user_text not in ACKNOWLEDGEMENTS:
            continue
        if turn.has_tool_activity or len(turn.assistant_text) > 240:
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
    groups = {}
    for turn in session.turns:
        text = _normalize(turn.user_text)
        if len(text) < 24:
            continue
        groups.setdefault(text, []).append(turn.number)

    findings = []
    for numbers in groups.values():
        if len(numbers) >= 2:
            findings.append(
                Finding(
                    kind="repeated_user_text",
                    turns=tuple(numbers),
                    title="Repeated user requirement",
                    detail="The same substantive user text appears in multiple turns.",
                    confidence=0.95,
                )
            )
    return findings


def detect_near_duplicate_user_text(session: NormalizedSession, threshold=0.88):
    candidates = [
        (turn.number, _normalize(turn.user_text))
        for turn in session.turns
        if len(_normalize(turn.user_text)) >= 40
    ]
    findings = []
    for i, (left_number, left_text) in enumerate(candidates):
        for right_number, right_text in candidates[i + 1:]:
            if left_text == right_text:
                continue
            score = SequenceMatcher(None, left_text, right_text).ratio()
            if score >= threshold:
                findings.append(
                    Finding(
                        kind="near_duplicate_user_text",
                        turns=(left_number, right_number),
                        title="Possible re-explanation",
                        detail=f"These user messages are very similar ({score:.0%} textual similarity).",
                        confidence=0.80,
                        mechanical=False,
                    )
                )
    return findings


def detect_correction_markers(session: NormalizedSession):
    findings = []
    for turn in session.turns:
        text = _normalize(turn.user_text)
        matched = next((marker for marker in CORRECTION_MARKERS if marker in text), None)
        if matched:
            findings.append(
                Finding(
                    kind="correction_marker",
                    turns=(turn.number,),
                    title="Possible correction loop",
                    detail=f'The user used "{matched}", which can indicate earlier context was lost or distorted.',
                    confidence=0.85,
                    mechanical=False,
                )
            )
    return findings


def detect_possible_contradictions(session: NormalizedSession, min_similarity=0.30):
    """Flag similar user requirements with opposite lexical polarity."""
    findings = []
    turns = [turn for turn in session.turns if len(turn.user_text.strip()) >= 20]

    for i, left in enumerate(turns):
        left_polarity = _polarity(left.user_text)
        if not left_polarity:
            continue
        for right in turns[i + 1:]:
            right_polarity = _polarity(right.user_text)
            if right_polarity != -left_polarity:
                continue
            similarity = _topic_similarity(left.user_text, right.user_text)
            if similarity < min_similarity:
                continue
            findings.append(
                Finding(
                    kind="possible_contradiction",
                    turns=(left.number, right.number),
                    title="Possible conflicting requirements",
                    detail=f"These requirements discuss similar terms but appear to point in opposite directions ({similarity:.0%} topic overlap).",
                    confidence=0.76,
                    mechanical=False,
                )
            )
    return findings


def detect_superseded_decisions(session: NormalizedSession, min_similarity=0.20):
    """Flag explicit replacement language and the nearest related earlier turn."""
    findings = []

    for index, turn in enumerate(session.turns):
        text = _normalize(turn.user_text)
        marker = next((m for m in SUPERSESSION_MARKERS if m in text), None)
        if not marker or index == 0:
            continue

        best = None
        for earlier in session.turns[max(0, index - 25):index]:
            similarity = _topic_similarity(earlier.user_text, turn.user_text)
            if best is None or similarity > best[0]:
                best = (similarity, earlier)

        if best and best[0] >= min_similarity:
            similarity, earlier = best
            findings.append(
                Finding(
                    kind="superseded_decision",
                    turns=(earlier.number, turn.number),
                    title="Possible superseded decision",
                    detail=f'Turn {turn.number} uses replacement language ("{marker.strip()}") and overlaps an earlier decision. Review which version is current.',
                    confidence=0.84,
                    mechanical=False,
                )
            )
    return findings


def _parse_timestamp(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_path(tool):
    name = tool.name.casefold()
    if name not in {"read", "read_file", "readfile", "cat"}:
        return None
    data = tool.input
    if isinstance(data, dict):
        for key in ("file_path", "path", "filename"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def detect_stale_file_reads(session: NormalizedSession, project_root=None):
    """Flag files modified on disk after the turn that read them."""
    findings = []
    root = Path(project_root).expanduser() if project_root else None

    for turn in session.turns:
        read_at = _parse_timestamp(turn.timestamp)
        if read_at is None:
            continue

        for tool in turn.tool_uses:
            raw_path = _read_path(tool)
            if not raw_path:
                continue
            path = Path(raw_path).expanduser()
            if not path.is_absolute() and root:
                path = root / path
            if not path.is_file():
                continue

            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=read_at.tzinfo)
            except OSError:
                continue

            if modified > read_at:
                findings.append(
                    Finding(
                        kind="stale_file_read",
                        turns=(turn.number,),
                        title="Stale file read",
                        detail=f"{path} changed after this turn read it. Earlier discussion may refer to an outdated file version.",
                        confidence=0.99,
                    )
                )
    return findings


def detect_pin_conflicts(session: NormalizedSession, pinned_texts):
    findings = []
    for pinned in pinned_texts or ():
        pinned = str(pinned).strip()
        if not pinned:
            continue
        pin_polarity = _polarity(pinned)
        for turn in session.turns:
            similarity = _topic_similarity(pinned, turn.user_text)
            if similarity < 0.30:
                continue
            turn_polarity = _polarity(turn.user_text)
            if pin_polarity and turn_polarity == -pin_polarity:
                findings.append(
                    Finding(
                        kind="source_of_truth_conflict",
                        turns=(turn.number,),
                        title="Possible source-of-truth conflict",
                        detail="This turn appears to conflict with a pinned project requirement.",
                        confidence=0.90,
                        mechanical=False,
                    )
                )
    return findings


def detect_large_tool_results(session: NormalizedSession, threshold=4000):
    findings = []
    for turn in session.turns:
        size = sum(result.char_count for result in turn.tool_results)
        if size >= threshold:
            findings.append(
                Finding(
                    kind="large_tool_output",
                    turns=(turn.number,),
                    title="Large tool output",
                    detail=f"Tool results in this turn contain about {size:,} characters.",
                    confidence=0.99,
                )
            )
    return findings


def detect_duplicate_tool_results(session: NormalizedSession, min_size=200):
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

    return [
        Finding(
            kind="duplicate_tool_output",
            turns=tuple(sorted(numbers)),
            title="Duplicate tool output",
            detail="Identical non-trivial tool-result content appears in multiple turns.",
            confidence=1.0,
        )
        for numbers in groups.values()
    ]


def analyze_session(session: NormalizedSession, project_root=None, pinned_texts=()):
    """Run all advisory detectors on a normalized provider-neutral session."""
    build_context_graph(session)

    detectors = (
        detect_lightweight_acknowledgements,
        detect_repeated_user_text,
        detect_near_duplicate_user_text,
        detect_correction_markers,
        detect_possible_contradictions,
        detect_superseded_decisions,
        detect_large_tool_results,
        detect_duplicate_tool_results,
    )

    findings = []
    for detector in detectors:
        findings.extend(detector(session))
    findings.extend(detect_stale_file_reads(session, project_root=project_root))
    findings.extend(detect_pin_conflicts(session, pinned_texts))
    return sorted(findings, key=lambda f: (min(f.turns), f.kind))


def analyze(entries, turns, project_root=None, pinned_texts=()):
    """Backward-compatible Claude Code analysis entry point."""
    return analyze_session(
        normalize(entries, turns),
        project_root=project_root,
        pinned_texts=pinned_texts,
    )
