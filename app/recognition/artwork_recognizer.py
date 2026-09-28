from __future__ import annotations

from app.cards.features import FeatureIndex
from app.recognition.models import CardObservation, DetectedCard


class ArtworkRecognizer:
    def __init__(self, feature_index: FeatureIndex) -> None:
        self.feature_index = feature_index

    def recognize(self, card: DetectedCard, *, top_k: int = 3) -> CardObservation:
        candidates = self.feature_index.match(
            card.image,
            query_is_full_card=True,
            top_k=top_k,
        )
        return CardObservation(
            source=card.source,
            candidates=tuple(candidates),
            polygon=card.polygon,
        )

