from pathlib import Path

import cv2
import numpy as np

from app.cards.features import FeatureIndex, color_histogram, difference_hash


def _write_fixture(path: Path, color: tuple[int, int, int]) -> None:
    image = np.zeros((614, 421, 3), dtype=np.uint8)
    image[:] = color
    cv2.rectangle(image, (50, 110), (370, 370), (255, 255, 255), 8)
    for index in range(12):
        center = (75 + (index % 4) * 85, 145 + (index // 4) * 90)
        radius = 12 + index
        marker_color = (
            (color[0] + index * 31) % 255,
            (color[1] + index * 47) % 255,
            (color[2] + index * 67) % 255,
        )
        cv2.circle(image, center, radius, marker_color, -1)
        cv2.putText(
            image,
            str(index),
            (center[0] - 8, center[1] + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    encoded.tofile(path)


def test_feature_shapes_are_stable() -> None:
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    assert difference_hash(image).shape == (256,)
    assert color_histogram(image).shape == (128,)


def test_feature_index_round_trip(tmp_path: Path) -> None:
    first = tmp_path / "1.jpg"
    second = tmp_path / "2.jpg"
    _write_fixture(first, (20, 40, 180))
    _write_fixture(second, (180, 40, 20))

    index = FeatureIndex.build({1: first, 2: second})
    path = tmp_path / "index.npz"
    index.save(path)
    loaded = FeatureIndex.load(path)

    assert loaded.card_ids.tolist() == [1, 2]
    assert loaded.difference_hashes.shape == (2, 256)
    assert loaded.color_histograms.shape == (2, 128)
    assert loaded.orb_counts.shape == (2,)
    assert loaded.orb_keypoint_blocks.shape[2] == 2


def test_feature_index_matches_source_card_first(tmp_path: Path) -> None:
    first = tmp_path / "1.jpg"
    second = tmp_path / "2.jpg"
    _write_fixture(first, (20, 40, 180))
    _write_fixture(second, (180, 40, 20))
    index = FeatureIndex.build({1: first, 2: second})

    query = cv2.imdecode(np.fromfile(first, dtype=np.uint8), cv2.IMREAD_COLOR)
    matches = index.match(query, query_is_full_card=True, top_k=2)

    assert matches[0].card_id == 1
    assert matches[0].score > matches[1].score


def test_locates_known_artwork_inside_larger_scene(tmp_path: Path) -> None:
    first = tmp_path / "1.jpg"
    second = tmp_path / "2.jpg"
    _write_fixture(first, (20, 40, 180))
    _write_fixture(second, (180, 40, 20))
    index = FeatureIndex.build({1: first, 2: second})

    source = cv2.imdecode(np.fromfile(first, dtype=np.uint8), cv2.IMREAD_COLOR)
    artwork = source[109:371, 48:373]
    scene = np.zeros((500, 900, 3), dtype=np.uint8)
    scene[110:372, 280:605] = artwork

    matches = index.locate_in_scene(scene, minimum_good_matches=4)

    assert matches
    assert matches[0].card_id == 1


def test_locates_two_copies_when_deck_allows_duplicates(tmp_path: Path) -> None:
    first = tmp_path / "1.jpg"
    _write_fixture(first, (20, 40, 180))
    index = FeatureIndex.build({1: first})

    source = cv2.imdecode(np.fromfile(first, dtype=np.uint8), cv2.IMREAD_COLOR)
    artwork = source[109:371, 48:373]
    scene = np.zeros((600, 1100, 3), dtype=np.uint8)
    scene[80:342, 90:415] = artwork
    scene[270:532, 670:995] = artwork

    matches = index.locate_in_scene(
        scene,
        minimum_good_matches=4,
        max_occurrences_by_card={1: 2},
    )

    assert [match.card_id for match in matches] == [1, 1]


def test_scene_lookup_respects_allowed_card_ids(tmp_path: Path) -> None:
    first = tmp_path / "1.jpg"
    second = tmp_path / "2.jpg"
    _write_fixture(first, (20, 40, 180))
    _write_fixture(second, (180, 40, 20))
    index = FeatureIndex.build({1: first, 2: second})

    source = cv2.imdecode(np.fromfile(first, dtype=np.uint8), cv2.IMREAD_COLOR)
    artwork = source[109:371, 48:373]
    scene = np.zeros((500, 900, 3), dtype=np.uint8)
    scene[110:372, 280:605] = artwork

    matches = index.locate_in_scene(
        scene,
        minimum_good_matches=4,
        allowed_card_ids={2},
    )
    assert all(match.card_id == 2 for match in matches)


def test_rejects_degenerate_projected_polygon() -> None:
    polygon = ((0, 25), (64, -56), (4, 27), (30, -36))

    assert not FeatureIndex._reasonable_scene_polygon(polygon, 125, 103)


