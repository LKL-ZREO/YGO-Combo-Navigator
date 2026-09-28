import cv2
import numpy as np

from app.recognition.card_geometry import detect_card_quads, warp_card


def test_detects_and_rectifies_card_quadrilateral() -> None:
    canvas = np.zeros((600, 900, 3), dtype=np.uint8)
    quad = np.asarray([[260, 70], [570, 100], [535, 545], [220, 510]], dtype=np.int32)
    cv2.fillConvexPoly(canvas, quad, (220, 220, 220))
    cv2.polylines(canvas, [quad], True, (255, 255, 255), 6)
    cv2.circle(canvas, (395, 280), 80, (30, 90, 220), -1)

    quads = detect_card_quads(canvas)

    assert quads
    warped = warp_card(canvas, quads[0])
    assert warped.shape[:2] == (614, 421)

