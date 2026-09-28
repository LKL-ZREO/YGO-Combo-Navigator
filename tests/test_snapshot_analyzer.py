from pathlib import Path

import cv2
import numpy as np

from app.cards.catalog import CardCatalog
from app.cards.features import FeatureIndex
from app.decks.ydk import load_ydk
from app.recognition.snapshot_analyzer import SnapshotAnalyzer
from app.roi.models import ROIProfile


def test_recognizes_overlapping_hand_without_false_empty_zone_matches() -> None:
    deck = load_ydk(
        Path("deck-packs/crimson-powerforce-md/crimson-powerforce-structure.ydk")
    )
    image_root = Path("data/cards/images")
    feature_index = FeatureIndex.build(
        {card_id: image_root / f"{card_id}.jpg" for card_id in set(deck.main)}
    )
    catalog = CardCatalog(Path("data/cards/catalog.json"))
    records = {
        record.card_id: record for record in catalog.get_many(deck.all_card_ids())
    }
    frame_path = Path("data/captures/recognition-diagnostic-current.png")
    frame = cv2.imdecode(np.fromfile(frame_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None

    analysis = SnapshotAnalyzer(
        ROIProfile.load(Path("roi-profiles/md-zh-hans-1920x1080.json")),
        deck,
        feature_index,
        records,
    ).analyze(frame)

    hand = next(region for region in analysis.regions if region.region_name == "self_hand")
    assert [match.card_id for match in hand.matches] == [
        34761841,  # Crimson Resonator
        23008320,  # Resonator Call
        8559524,  # Resonator Command
        5376159,  # Red Reign
        24662957,  # Fiendish Golem
    ]
    assert all(
        not region.matches
        for region in analysis.regions
        if region.region_name != "self_hand"
    )
