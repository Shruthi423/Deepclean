"""Shared finding model and review policy for context analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ReviewLevel = Literal["strong", "possible"]


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

    @property
    def review_level(self) -> ReviewLevel:
        return "strong" if self.confidence >= 0.95 else "possible"
