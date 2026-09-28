from pathlib import Path

import pytest

from app.roi.models import NormalizedROI, ROIProfile


def test_default_profile_loads_and_has_unique_regions() -> None:
    path = Path("roi-profiles/md-zh-hans-1920x1080.json")
    profile = ROIProfile.load(path)

    assert profile.reference_width == 1920
    assert profile.reference_height == 1080
    assert profile.get_region("self_hand").label == "我方手牌"
    assert len({region.name for region in profile.regions}) == len(profile.regions)


def test_normalized_roi_resolves_to_pixels() -> None:
    roi = NormalizedROI(
        name="test",
        label="Test",
        x=0.25,
        y=0.5,
        width=0.5,
        height=0.25,
    )

    rect = roi.resolve(1920, 1080)

    assert rect.left == 480
    assert rect.top == 540
    assert rect.width == 960
    assert rect.height == 270


def test_roi_rejects_out_of_bounds_region() -> None:
    roi = NormalizedROI(
        name="bad",
        label="Bad",
        x=0.9,
        y=0.2,
        width=0.2,
        height=0.2,
    )

    with pytest.raises(ValueError, match="extends beyond"):
        roi.validate()

