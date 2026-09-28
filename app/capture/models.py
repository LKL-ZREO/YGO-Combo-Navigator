from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class PixelRect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Invalid capture rectangle: {self}")


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    client_rect: PixelRect

    @property
    def display_name(self) -> str:
        return f"{self.title} ({self.client_rect.width}×{self.client_rect.height})"


@dataclass(frozen=True, slots=True)
class StableCapture:
    frame: np.ndarray
    motion_score: float
    is_stable: bool
    sampled_frames: int

