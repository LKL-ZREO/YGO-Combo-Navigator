from __future__ import annotations

import cv2
import numpy as np

from app.recognition.models import DetectedCard


CARD_ASPECT_RATIO = 421 / 614


def order_quad(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    result = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    result[0] = points[np.argmin(sums)]
    result[2] = points[np.argmax(sums)]
    result[1] = points[np.argmin(differences)]
    result[3] = points[np.argmax(differences)]
    return result


def warp_card(image: np.ndarray, quad: np.ndarray, *, height: int = 614) -> np.ndarray:
    ordered = order_quad(quad)
    width = round(height * CARD_ASPECT_RATIO)
    destination = np.asarray(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(ordered, destination)
    return cv2.warpPerspective(image, transform, (width, height))


def detect_card_quads(
    image: np.ndarray,
    *,
    min_area_ratio: float = 0.018,
    max_area_ratio: float = 0.9,
) -> list[np.ndarray]:
    if image.size == 0:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 135)
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        iterations=2,
    )
    contours, _hierarchy = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = image.shape[0] * image.shape[1]
    candidates: list[tuple[float, np.ndarray]] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        ratio = area / image_area
        if ratio < min_area_ratio or ratio > max_area_ratio:
            continue
        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approximation) != 4 or not cv2.isContourConvex(approximation):
            continue
        rect = cv2.minAreaRect(approximation)
        short_side, long_side = sorted(rect[1])
        if short_side <= 0:
            continue
        aspect = short_side / long_side
        if not 0.48 <= aspect <= 0.88:
            continue
        candidates.append((area, approximation.reshape(4, 2)))

    candidates.sort(key=lambda item: item[0], reverse=True)
    accepted: list[np.ndarray] = []
    for _area, quad in candidates:
        center = quad.mean(axis=0)
        if any(np.linalg.norm(center - existing.mean(axis=0)) < 18 for existing in accepted):
            continue
        accepted.append(quad)
    return sorted(accepted, key=lambda quad: float(quad[:, 0].mean()))


def detect_cards(image: np.ndarray, *, source: str) -> list[DetectedCard]:
    return [
        DetectedCard(
            source=source,
            image=warp_card(image, quad),
            polygon=tuple((int(x), int(y)) for x, y in quad),
        )
        for quad in detect_card_quads(image)
    ]

