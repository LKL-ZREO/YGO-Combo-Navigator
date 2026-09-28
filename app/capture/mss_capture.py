from __future__ import annotations

from typing import Protocol

import mss
import numpy as np

from app.capture.models import PixelRect, WindowInfo


class FrameProvider(Protocol):
    def capture_window(self, window: WindowInfo) -> np.ndarray:
        """Return a BGR uint8 frame for the selected window client area."""


class MSSWindowCapture:
    def capture_rect(self, rect: PixelRect) -> np.ndarray:
        rect.validate()
        monitor = {
            "left": rect.left,
            "top": rect.top,
            "width": rect.width,
            "height": rect.height,
        }
        with mss.mss() as grabber:
            bgra = np.asarray(grabber.grab(monitor), dtype=np.uint8)
        return np.ascontiguousarray(bgra[:, :, :3])

    def capture_window(self, window: WindowInfo) -> np.ndarray:
        return self.capture_rect(window.client_rect)

