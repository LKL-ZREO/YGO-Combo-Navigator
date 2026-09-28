from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.cards.catalog import CardRecord
from app.cards.features import FeatureIndex, LocatedCardMatch
from app.decks.models import DeckList
from app.roi.models import ROIProfile


@dataclass(frozen=True, slots=True)
class RegionAnalysis:
    region_name: str
    matches: tuple[LocatedCardMatch, ...]


@dataclass(frozen=True, slots=True)
class SnapshotAnalysis:
    regions: tuple[RegionAnalysis, ...]

    @property
    def matches(self) -> tuple[LocatedCardMatch, ...]:
        return tuple(match for region in self.regions for match in region.matches)


class SnapshotAnalyzer:
    def __init__(
        self,
        profile: ROIProfile,
        deck: DeckList,
        feature_index: FeatureIndex,
        records: dict[int, CardRecord],
    ) -> None:
        self.profile = profile
        self.deck = deck
        self.feature_index = feature_index
        self.records = records

    def analyze(self, frame: np.ndarray) -> SnapshotAnalysis:
        height, width = frame.shape[:2]
        deck_counts = {card_id: count for card_id, count in self.deck.counts().items()}
        main_card_ids = set(self.deck.main)
        monster_card_ids = {
            card_id
            for card_id, record in self.records.items()
            if "Monster" in record.card_type
        }
        spell_trap_card_ids = {
            card_id
            for card_id, record in self.records.items()
            if "Spell" in record.card_type or "Trap" in record.card_type
        }
        analyses: list[RegionAnalysis] = []

        hand_region = self.profile.get_region("self_hand")
        hand_rect = hand_region.resolve(width, height)
        hand_image = frame[hand_rect.top : hand_rect.bottom, hand_rect.left : hand_rect.right]
        hand_matches = self.feature_index.locate_partial_artworks(
            hand_image,
            minimum_good_matches=5,
            minimum_inlier_ratio=0.60,
            minimum_score=0.48,
            limit=15,
            max_occurrences_by_card=deck_counts,
            allowed_card_ids=main_card_ids,
        )
        analyses.append(
            RegionAnalysis(
                region_name="self_hand",
                matches=tuple(self._offset_matches(hand_matches, hand_rect.left, hand_rect.top)),
            )
        )

        zone_names = [
            region.name
            for region in self.profile.regions
            if region.name.startswith("self_monster_")
            or region.name.startswith("shared_extra_monster_")
            or region.name.startswith("self_spell_")
            or region.name == "self_field_zone"
        ]
        for region_name in zone_names:
            region = self.profile.get_region(region_name)
            rect = region.resolve(width, height)
            crop = frame[rect.top : rect.bottom, rect.left : rect.right]
            if region_name.startswith(("self_monster_", "shared_extra_monster_")):
                allowed_card_ids = monster_card_ids
            else:
                allowed_card_ids = spell_trap_card_ids
            # Field cards are rendered much smaller than the source artwork and
            # may be covered by ATK/DEF or activation UI.  SIFT-based partial
            # artwork matching is scale-stable enough for these zone crops,
            # whereas the ORB scene matcher frequently produces fewer than the
            # required number of correspondences.
            matches = self.feature_index.locate_partial_artworks(
                crop,
                minimum_good_matches=5,
                minimum_inlier_ratio=0.60,
                minimum_score=0.48,
                limit=1,
                max_occurrences_by_card={card_id: 1 for card_id in deck_counts},
                allowed_card_ids=allowed_card_ids,
            )
            analyses.append(
                RegionAnalysis(
                    region_name=region_name,
                    matches=tuple(self._offset_matches(matches, rect.left, rect.top)),
                )
            )
        return SnapshotAnalysis(regions=tuple(analyses))

    @staticmethod
    def _offset_matches(
        matches: list[LocatedCardMatch],
        offset_x: int,
        offset_y: int,
    ) -> list[LocatedCardMatch]:
        return [
            LocatedCardMatch(
                card_id=match.card_id,
                score=match.score,
                good_matches=match.good_matches,
                inlier_ratio=match.inlier_ratio,
                polygon=tuple((x + offset_x, y + offset_y) for x, y in match.polygon),
            )
            for match in matches
        ]

