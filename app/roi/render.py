from __future__ import annotations

import cv2
import numpy as np

from app.roi.models import ROIProfile


def render_roi_overlay(
    frame: np.ndarray,
    profile: ROIProfile,
    *,
    selected_name: str | None = None,
) -> np.ndarray:
    output = np.ascontiguousarray(frame.copy())
    frame_height, frame_width = output.shape[:2]

    for region in profile.regions:
        rect = region.resolve(frame_width, frame_height)
        color = tuple(int(channel) for channel in region.color[::-1])
        thickness = 3 if region.name == selected_name else 1
        cv2.rectangle(
            output,
            (rect.left, rect.top),
            (rect.right, rect.bottom),
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )
        label_y = max(18, rect.top - 5)
        cv2.putText(
            output,
            region.label,
            (rect.left + 3, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    return output

