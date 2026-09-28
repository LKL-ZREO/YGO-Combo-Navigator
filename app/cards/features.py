from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class CardFeature:
    card_id: int
    difference_hash: np.ndarray
    color_histogram: np.ndarray
    orb_descriptors: np.ndarray
    orb_keypoints: np.ndarray
    sift_descriptors: np.ndarray
    sift_keypoints: np.ndarray


@dataclass(frozen=True, slots=True)
class CandidateMatch:
    card_id: int
    score: float
    hash_score: float
    color_score: float
    local_feature_score: float


@dataclass(frozen=True, slots=True)
class LocatedCardMatch:
    card_id: int
    score: float
    good_matches: int
    inlier_ratio: float
    polygon: tuple[tuple[int, int], ...]


def crop_artwork(card_image: np.ndarray) -> np.ndarray:
    """Crop the illustration box from a standard full-card scan."""

    height, width = card_image.shape[:2]
    left = round(width * 0.115)
    right = round(width * 0.885)
    top = round(height * 0.178)
    bottom = round(height * 0.605)
    crop = card_image[top:bottom, left:right]
    if crop.size == 0:
        raise ValueError("Artwork crop is empty")
    return np.ascontiguousarray(crop)


def difference_hash(image: np.ndarray, *, hash_size: int = 16) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    return (resized[:, 1:] > resized[:, :-1]).astype(np.uint8).reshape(-1)


def color_histogram(image: np.ndarray, *, bins: tuple[int, int] = (16, 8)) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, list(bins), [0, 180, 0, 256])
    cv2.normalize(histogram, histogram, alpha=1.0, norm_type=cv2.NORM_L1)
    return histogram.astype(np.float32).reshape(-1)


def orb_features(
    image: np.ndarray,
    *,
    max_features: int = 400,
) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detector = cv2.ORB_create(nfeatures=max_features, fastThreshold=8)
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    if descriptors is None:
        return (
            np.empty((0, 32), dtype=np.uint8),
            np.empty((0, 2), dtype=np.float32),
        )
    height, width = gray.shape
    normalized_keypoints = np.asarray(
        [[point.pt[0] / width, point.pt[1] / height] for point in keypoints],
        dtype=np.float32,
    )
    return descriptors.astype(np.uint8), normalized_keypoints


def orb_descriptors(image: np.ndarray, *, max_features: int = 400) -> np.ndarray:
    descriptors, _keypoints = orb_features(image, max_features=max_features)
    return descriptors


def sift_features(
    image: np.ndarray,
    *,
    max_features: int = 800,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract scale-stable features for small, partially visible card artwork."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detector = cv2.SIFT_create(
        nfeatures=max_features,
        contrastThreshold=0.01,
        edgeThreshold=12,
    )
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    if descriptors is None:
        return (
            np.empty((0, 128), dtype=np.float32),
            np.empty((0, 2), dtype=np.float32),
        )
    height, width = gray.shape
    normalized_keypoints = np.asarray(
        [[point.pt[0] / width, point.pt[1] / height] for point in keypoints],
        dtype=np.float32,
    )
    return descriptors.astype(np.float32), normalized_keypoints


def extract_feature(card_id: int, image_path: Path) -> CardFeature:
    card_image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if card_image is None:
        raise ValueError(f"Unable to read card artwork: {image_path}")
    artwork = crop_artwork(card_image)
    descriptors, keypoints = orb_features(artwork)
    sift_descriptors, sift_keypoints = sift_features(artwork)
    return CardFeature(
        card_id=card_id,
        difference_hash=difference_hash(artwork),
        color_histogram=color_histogram(artwork),
        orb_descriptors=descriptors,
        orb_keypoints=keypoints,
        sift_descriptors=sift_descriptors,
        sift_keypoints=sift_keypoints,
    )


class FeatureIndex:
    def __init__(self, features: list[CardFeature]) -> None:
        if not features:
            raise ValueError("Feature index requires at least one card")
        self.card_ids = np.asarray([feature.card_id for feature in features], dtype=np.int64)
        self.difference_hashes = np.stack(
            [feature.difference_hash for feature in features]
        ).astype(np.uint8)
        self.color_histograms = np.stack(
            [feature.color_histogram for feature in features]
        ).astype(np.float32)
        self.orb_counts = np.asarray(
            [len(feature.orb_descriptors) for feature in features], dtype=np.int32
        )
        descriptor_width = 32
        max_descriptor_count = max(1, int(self.orb_counts.max(initial=0)))
        self.orb_descriptor_blocks = np.zeros(
            (len(features), max_descriptor_count, descriptor_width), dtype=np.uint8
        )
        self.orb_keypoint_blocks = np.zeros(
            (len(features), max_descriptor_count, 2), dtype=np.float32
        )
        for index, feature in enumerate(features):
            count = len(feature.orb_descriptors)
            if count:
                self.orb_descriptor_blocks[index, :count] = feature.orb_descriptors
                self.orb_keypoint_blocks[index, :count] = feature.orb_keypoints

        self.sift_counts = np.asarray(
            [len(feature.sift_descriptors) for feature in features], dtype=np.int32
        )
        max_sift_count = max(1, int(self.sift_counts.max(initial=0)))
        self.sift_descriptor_blocks = np.zeros(
            (len(features), max_sift_count, 128), dtype=np.float32
        )
        self.sift_keypoint_blocks = np.zeros(
            (len(features), max_sift_count, 2), dtype=np.float32
        )
        for index, feature in enumerate(features):
            count = len(feature.sift_descriptors)
            if count:
                self.sift_descriptor_blocks[index, :count] = feature.sift_descriptors
                self.sift_keypoint_blocks[index, :count] = feature.sift_keypoints

    @classmethod
    def build(cls, card_images: dict[int, Path]) -> "FeatureIndex":
        return cls(
            [extract_feature(card_id, path) for card_id, path in sorted(card_images.items())]
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            card_ids=self.card_ids,
            difference_hashes=self.difference_hashes,
            color_histograms=self.color_histograms,
            orb_counts=self.orb_counts,
            orb_descriptor_blocks=self.orb_descriptor_blocks,
            orb_keypoint_blocks=self.orb_keypoint_blocks,
            sift_counts=self.sift_counts,
            sift_descriptor_blocks=self.sift_descriptor_blocks,
            sift_keypoint_blocks=self.sift_keypoint_blocks,
        )

    @classmethod
    def load(cls, path: Path) -> "FeatureIndex":
        with np.load(path, allow_pickle=False) as payload:
            card_ids = payload["card_ids"]
            hashes = payload["difference_hashes"]
            histograms = payload["color_histograms"]
            counts = payload["orb_counts"]
            descriptor_blocks = payload["orb_descriptor_blocks"]
            keypoint_blocks = payload["orb_keypoint_blocks"]
            if "sift_counts" in payload.files:
                sift_counts = payload["sift_counts"]
                sift_descriptor_blocks = payload["sift_descriptor_blocks"]
                sift_keypoint_blocks = payload["sift_keypoint_blocks"]
            else:
                sift_counts = np.zeros(len(card_ids), dtype=np.int32)
                sift_descriptor_blocks = np.zeros(
                    (len(card_ids), 1, 128), dtype=np.float32
                )
                sift_keypoint_blocks = np.zeros(
                    (len(card_ids), 1, 2), dtype=np.float32
                )
        features = [
            CardFeature(
                int(card_id),
                hashes[index],
                histograms[index],
                descriptor_blocks[index, : counts[index]],
                keypoint_blocks[index, : counts[index]],
                sift_descriptor_blocks[index, : sift_counts[index]],
                sift_keypoint_blocks[index, : sift_counts[index]],
            )
            for index, card_id in enumerate(card_ids)
        ]
        return cls(features)

    def locate_partial_artworks(
        self,
        scene: np.ndarray,
        *,
        minimum_good_matches: int = 5,
        minimum_inlier_ratio: float = 0.60,
        minimum_score: float = 0.48,
        limit: int = 15,
        max_occurrences_by_card: dict[int, int] | None = None,
        allowed_card_ids: set[int] | None = None,
    ) -> list[LocatedCardMatch]:
        """Locate small or overlapping cards from the visible part of their artwork."""

        scene_descriptors, scene_keypoints = sift_features(scene, max_features=1200)
        if not len(scene_descriptors):
            return []

        located: list[LocatedCardMatch] = []
        for index, card_id in enumerate(self.card_ids):
            numeric_card_id = int(card_id)
            if allowed_card_ids is not None and numeric_card_id not in allowed_card_ids:
                continue
            maximum = (max_occurrences_by_card or {}).get(numeric_card_id, 1)
            located.extend(
                self._locate_partial_occurrences(
                    index,
                    numeric_card_id,
                    scene_descriptors,
                    scene_keypoints,
                    scene.shape[1],
                    scene.shape[0],
                    maximum=maximum,
                    minimum_good_matches=minimum_good_matches,
                    minimum_inlier_ratio=minimum_inlier_ratio,
                    minimum_score=minimum_score,
                )
            )
        return self._suppress_overlapping_matches(located)[:limit]

    def _locate_partial_occurrences(
        self,
        index: int,
        card_id: int,
        scene_descriptors: np.ndarray,
        scene_keypoints: np.ndarray,
        scene_width: int,
        scene_height: int,
        *,
        maximum: int,
        minimum_good_matches: int,
        minimum_inlier_ratio: float,
        minimum_score: float,
    ) -> list[LocatedCardMatch]:
        count = int(self.sift_counts[index])
        if count < minimum_good_matches or maximum <= 0:
            return []

        stored_descriptors = self.sift_descriptor_blocks[index, :count]
        remaining_indices = np.arange(len(scene_descriptors))
        matcher = cv2.BFMatcher(cv2.NORM_L2)
        results: list[LocatedCardMatch] = []

        for _occurrence in range(maximum):
            if len(remaining_indices) < minimum_good_matches:
                break
            remaining_descriptors = scene_descriptors[remaining_indices]
            pairs = matcher.knnMatch(stored_descriptors, remaining_descriptors, k=2)
            good = [
                pair[0]
                for pair in pairs
                if len(pair) == 2 and pair[0].distance < 0.72 * pair[1].distance
            ]
            if len(good) < minimum_good_matches:
                break

            source_points = np.float32(
                [self.sift_keypoint_blocks[index, match.queryIdx] for match in good]
            ).reshape(-1, 1, 2)
            destination_points = np.float32(
                [scene_keypoints[remaining_indices[match.trainIdx]] for match in good]
            )
            destination_points[:, 0] *= scene_width
            destination_points[:, 1] *= scene_height
            destination_points = destination_points.reshape(-1, 1, 2)
            homography, mask = cv2.findHomography(
                source_points,
                destination_points,
                cv2.RANSAC,
                max(3.0, min(scene_width, scene_height) * 0.022),
            )
            if homography is None or mask is None:
                break

            inlier_count = int(mask.sum())
            inlier_ratio = float(mask.mean())
            if inlier_count < minimum_good_matches or inlier_ratio < minimum_inlier_ratio:
                break

            normalized_corners = np.float32([[[0, 0], [1, 0], [1, 1], [0, 1]]])
            projected = cv2.perspectiveTransform(normalized_corners, homography)[0]
            polygon = tuple((int(round(x)), int(round(y))) for x, y in projected)
            match_strength = min(1.0, inlier_count / 20.0)
            score = 0.55 * match_strength + 0.45 * inlier_ratio
            if score < minimum_score or not self._reasonable_scene_polygon(
                polygon,
                scene_width,
                scene_height,
            ):
                break

            results.append(
                LocatedCardMatch(
                    card_id=card_id,
                    score=float(score),
                    good_matches=inlier_count,
                    inlier_ratio=inlier_ratio,
                    polygon=polygon,
                )
            )
            polygon_points = np.asarray(polygon, dtype=np.float32)
            remaining_points = scene_keypoints[remaining_indices].copy()
            remaining_points[:, 0] *= scene_width
            remaining_points[:, 1] *= scene_height
            inside = np.asarray(
                [
                    cv2.pointPolygonTest(polygon_points, tuple(point), False) >= 0
                    for point in remaining_points
                ]
            )
            if not inside.any():
                break
            remaining_indices = remaining_indices[~inside]
        return results

    @staticmethod
    def _suppress_overlapping_matches(
        matches: list[LocatedCardMatch],
    ) -> list[LocatedCardMatch]:
        accepted: list[LocatedCardMatch] = []
        for match in sorted(matches, key=lambda item: item.score, reverse=True):
            polygon = np.asarray(match.polygon, dtype=np.float32)
            area = abs(float(cv2.contourArea(polygon)))
            overlaps_existing = False
            for existing in accepted:
                existing_polygon = np.asarray(existing.polygon, dtype=np.float32)
                existing_area = abs(float(cv2.contourArea(existing_polygon)))
                intersection, _shape = cv2.intersectConvexConvex(
                    polygon,
                    existing_polygon,
                )
                union = area + existing_area - float(intersection)
                if union > 0 and float(intersection) / union >= 0.40:
                    overlaps_existing = True
                    break
            if not overlaps_existing:
                accepted.append(match)
        return sorted(
            accepted,
            key=lambda item: float(np.mean(np.asarray(item.polygon)[:, 0])),
        )

    def locate_in_scene(
        self,
        scene: np.ndarray,
        *,
        minimum_good_matches: int = 6,
        minimum_score: float = 0.24,
        limit: int = 10,
        max_occurrences_by_card: dict[int, int] | None = None,
        allowed_card_ids: set[int] | None = None,
    ) -> list[LocatedCardMatch]:
        scene_descriptors, scene_keypoints = orb_features(scene, max_features=1600)
        if not len(scene_descriptors):
            return []

        located: list[LocatedCardMatch] = []
        for index, card_id in enumerate(self.card_ids):
            if allowed_card_ids is not None and int(card_id) not in allowed_card_ids:
                continue
            maximum = (max_occurrences_by_card or {}).get(int(card_id), 1)
            located.extend(
                self._locate_card_occurrences(
                    index,
                    int(card_id),
                    scene_descriptors,
                    scene_keypoints,
                    scene.shape[1],
                    scene.shape[0],
                    maximum=maximum,
                    minimum_good_matches=minimum_good_matches,
                    minimum_score=minimum_score,
                )
            )
        return sorted(located, key=lambda item: item.score, reverse=True)[:limit]

    def _locate_card_occurrences(
        self,
        index: int,
        card_id: int,
        scene_descriptors: np.ndarray,
        scene_keypoints: np.ndarray,
        scene_width: int,
        scene_height: int,
        *,
        maximum: int,
        minimum_good_matches: int,
        minimum_score: float,
    ) -> list[LocatedCardMatch]:
        count = int(self.orb_counts[index])
        if count < minimum_good_matches or maximum <= 0:
            return []
        stored_descriptors = self.orb_descriptor_blocks[index, :count]
        remaining_indices = np.arange(len(scene_descriptors))
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        results: list[LocatedCardMatch] = []

        for _occurrence in range(maximum):
            if len(remaining_indices) < minimum_good_matches:
                break
            remaining_descriptors = scene_descriptors[remaining_indices]
            pairs = matcher.knnMatch(stored_descriptors, remaining_descriptors, k=2)
            good = [
                pair[0]
                for pair in pairs
                if len(pair) == 2 and pair[0].distance < 0.76 * pair[1].distance
            ]
            if len(good) < minimum_good_matches:
                break
            source_points = np.float32(
                [self.orb_keypoint_blocks[index, match.queryIdx] for match in good]
            ).reshape(-1, 1, 2)
            destination_points = np.float32(
                [scene_keypoints[remaining_indices[match.trainIdx]] for match in good]
            ).reshape(-1, 1, 2)
            homography, mask = cv2.findHomography(
                source_points,
                destination_points,
                cv2.RANSAC,
                0.02,
            )
            if homography is None or mask is None:
                break
            inlier_count = int(mask.sum())
            inlier_ratio = float(mask.mean())
            if inlier_count < max(5, minimum_good_matches) or inlier_ratio < 0.55:
                break
            match_strength = min(1.0, len(good) / 25.0)
            score = 0.6 * match_strength + 0.4 * inlier_ratio
            normalized_corners = np.float32([[[0, 0], [1, 0], [1, 1], [0, 1]]])
            projected = cv2.perspectiveTransform(normalized_corners, homography)[0]
            projected[:, 0] *= scene_width
            projected[:, 1] *= scene_height
            polygon = tuple((int(round(x)), int(round(y))) for x, y in projected)
            if score < minimum_score or not self._reasonable_scene_polygon(
                polygon,
                scene_width,
                scene_height,
            ):
                break
            results.append(
                LocatedCardMatch(
                    card_id=card_id,
                    score=float(score),
                    good_matches=len(good),
                    inlier_ratio=inlier_ratio,
                    polygon=polygon,
                )
            )
            polygon_points = np.asarray(polygon, dtype=np.float32)
            remaining_points = scene_keypoints[remaining_indices].copy()
            remaining_points[:, 0] *= scene_width
            remaining_points[:, 1] *= scene_height
            inside = np.asarray(
                [cv2.pointPolygonTest(polygon_points, tuple(point), False) >= 0 for point in remaining_points]
            )
            if not inside.any():
                break
            remaining_indices = remaining_indices[~inside]
        return results

    @staticmethod
    def _reasonable_scene_polygon(
        polygon: tuple[tuple[int, int], ...],
        width: int,
        height: int,
    ) -> bool:
        points = np.asarray(polygon, dtype=np.float32)
        area = abs(float(cv2.contourArea(points)))
        scene_area = width * height
        if area < scene_area * 0.008 or area > scene_area * 0.92:
            return False
        if not cv2.isContourConvex(points.astype(np.int32)):
            return False

        edge_lengths = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
        if float(edge_lengths.min()) < max(8.0, min(width, height) * 0.10):
            return False

        bounding_width = float(points[:, 0].max() - points[:, 0].min())
        bounding_height = float(points[:, 1].max() - points[:, 1].min())
        if bounding_width <= 0 or bounding_height <= 0:
            return False
        if area / (bounding_width * bounding_height) < 0.45:
            return False

        margin_x = width * 0.12
        margin_y = height * 0.12
        return bool(
            np.all(points[:, 0] >= -margin_x)
            and np.all(points[:, 0] <= width + margin_x)
            and np.all(points[:, 1] >= -margin_y)
            and np.all(points[:, 1] <= height + margin_y)
        )

    def match(
        self,
        query: np.ndarray,
        *,
        query_is_full_card: bool = False,
        top_k: int = 3,
    ) -> list[CandidateMatch]:
        if query.size == 0:
            raise ValueError("Query image is empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        artwork = crop_artwork(query) if query_is_full_card else query
        query_hash = difference_hash(artwork)
        query_histogram = color_histogram(artwork)
        query_descriptors = orb_descriptors(artwork)

        hash_scores = 1.0 - np.mean(
            np.not_equal(self.difference_hashes, query_hash), axis=1
        )
        color_scores = np.asarray(
            [
                max(
                    0.0,
                    min(
                        1.0,
                        float(
                            cv2.compareHist(
                                stored.reshape(-1, 1),
                                query_histogram.reshape(-1, 1),
                                cv2.HISTCMP_CORREL,
                            )
                        ),
                    ),
                )
                for stored in self.color_histograms
            ],
            dtype=np.float32,
        )
        local_scores = np.asarray(
            [self._orb_similarity(query_descriptors, index) for index in range(len(self.card_ids))],
            dtype=np.float32,
        )
        final_scores = 0.25 * hash_scores + 0.20 * color_scores + 0.55 * local_scores
        best_indices = np.argsort(final_scores)[::-1][: min(top_k, len(self.card_ids))]
        return [
            CandidateMatch(
                card_id=int(self.card_ids[index]),
                score=float(final_scores[index]),
                hash_score=float(hash_scores[index]),
                color_score=float(color_scores[index]),
                local_feature_score=float(local_scores[index]),
            )
            for index in best_indices
        ]

    def _orb_similarity(self, query_descriptors: np.ndarray, index: int) -> float:
        count = int(self.orb_counts[index])
        if not len(query_descriptors) or not count:
            return 0.0
        stored = self.orb_descriptor_blocks[index, :count]
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        pairs = matcher.knnMatch(query_descriptors, stored, k=2)
        good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.76 * pair[1].distance]
        denominator = max(8, min(len(query_descriptors), count, 40))
        return min(1.0, len(good) / denominator)

