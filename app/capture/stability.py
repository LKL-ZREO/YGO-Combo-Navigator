from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from app.capture.models import StableCapture, WindowInfo
from app.capture.mss_capture import FrameProvider


@dataclass(slots=True)
class StableFrameSelector:
    sample_count: int = 3
    interval_ms: int = 90
    stable_threshold: float = 2.5
    analysis_size: tuple[int, int] = (320, 180)

    def __post_init__(self) -> None:
        if self.sample_count < 2:
            raise ValueError("sample_count must be at least 2")
        if self.interval_ms < 0:
            raise ValueError("interval_ms cannot be negative")

    def capture(self, provider: FrameProvider, window: WindowInfo) -> StableCapture:
        frames: list[np.ndarray] = []
        for index in range(self.sample_count):
            frames.append(provider.capture_window(window))
            if index + 1 < self.sample_count and self.interval_ms:
                time.sleep(self.interval_ms / 1000)
        return self.select_from_frames(frames)

    def select_from_frames(self, frames: list[np.ndarray]) -> StableCapture:
        if len(frames) < 2:
            raise ValueError("At least two frames are required")

        expected_shape = frames[0].shape
        if any(frame.shape != expected_shape for frame in frames):
            raise ValueError("All sampled frames must have the same shape")

        prepared = [self._prepare(frame) for frame in frames]
        scores = [
            float(cv2.absdiff(prepared[index - 1], prepared[index]).mean())
            for index in range(1, len(prepared))
        ]
        best_pair_index = int(np.argmin(scores))
        selected_frame = frames[best_pair_index + 1]
        best_score = scores[best_pair_index]
        return StableCapture(
            frame=np.ascontiguousarray(selected_frame),
            motion_score=best_score,
            is_stable=best_score <= self.stable_threshold,
            sampled_frames=len(frames),
        )

    def _prepare(self, frame: np.ndarray) -> np.ndarray:
        resized = cv2.resize(frame, self.analysis_size, interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

