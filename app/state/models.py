from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field as dataclass_field
from enum import StrEnum


class UsageState(StrEnum):
    AVAILABLE = "AVAILABLE"
    USED = "USED"
    UNKNOWN = "UNKNOWN"


class Phase(StrEnum):
    MAIN1 = "MAIN1"
    MAIN2 = "MAIN2"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class DuelState:
    hand: Counter[int] = dataclass_field(default_factory=Counter)
    field: Counter[int] = dataclass_field(default_factory=Counter)
    known_graveyard: Counter[int] = dataclass_field(default_factory=Counter)
    known_banished: Counter[int] = dataclass_field(default_factory=Counter)
    phase: Phase = Phase.UNKNOWN
    normal_summon: UsageState = UsageState.UNKNOWN
    used_effects: dict[str, UsageState] = dataclass_field(default_factory=dict)
    active_restrictions: set[str] = dataclass_field(default_factory=set)
    recognition_confidence: float = 1.0

    def copy(self) -> "DuelState":
        return DuelState(
            hand=self.hand.copy(),
            field=self.field.copy(),
            known_graveyard=self.known_graveyard.copy(),
            known_banished=self.known_banished.copy(),
            phase=self.phase,
            normal_summon=self.normal_summon,
            used_effects=dict(self.used_effects),
            active_restrictions=set(self.active_restrictions),
            recognition_confidence=self.recognition_confidence,
        )

