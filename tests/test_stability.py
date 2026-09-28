import numpy as np

from app.capture.stability import StableFrameSelector


def test_selector_picks_frame_from_least_changed_pair() -> None:
    first = np.zeros((200, 300, 3), dtype=np.uint8)
    second = np.full((200, 300, 3), 100, dtype=np.uint8)
    third = np.full((200, 300, 3), 101, dtype=np.uint8)

    selector = StableFrameSelector(sample_count=3, stable_threshold=2.5)
    result = selector.select_from_frames([first, second, third])

    assert np.array_equal(result.frame, third)
    assert result.motion_score == 1.0
    assert result.is_stable is True


def test_selector_marks_large_motion_as_unstable() -> None:
    first = np.zeros((100, 100, 3), dtype=np.uint8)
    second = np.full((100, 100, 3), 50, dtype=np.uint8)

    selector = StableFrameSelector(sample_count=2, stable_threshold=2.5)
    result = selector.select_from_frames([first, second])

    assert result.is_stable is False
    assert result.motion_score == 50.0

