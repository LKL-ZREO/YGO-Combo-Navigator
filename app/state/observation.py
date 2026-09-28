from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.state.models import Phase, UsageState


@dataclass(frozen=True, slots=True)
class BoardObservation:
    hand: Counter[int] | None = None
    field: Counter[int] | None = None
    known_graveyard: Counter[int] | None = None
    known_banished: Counter[int] | None = None
    phase: Phase | None = None
    normal_summon: UsageState | None = None
    used_effects: dict[str, UsageState] | None = None
    active_restrictions: set[str] | None = None
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Observation confidence must be between 0 and 1")

