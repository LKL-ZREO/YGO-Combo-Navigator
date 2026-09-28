from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.cards.features import CandidateMatch


@dataclass(frozen=True, slots=True)
class DetectedCard:
    source: str
    image: np.ndarray
    polygon: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class CardObservation:
    source: str
    candidates: tuple[CandidateMatch, ...]
    polygon: tuple[tuple[int, int], ...]

    @property
    def best(self) -> CandidateMatch | None:
        return self.candidates[0] if self.candidates else None

    @property
    def margin(self) -> float:
        if len(self.candidates) < 2:
            return self.candidates[0].score if self.candidates else 0.0
        return self.candidates[0].score - self.candidates[1].score

