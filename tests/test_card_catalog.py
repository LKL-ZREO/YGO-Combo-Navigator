import json

from app.cards.catalog import CardCatalog, CardNameLocalizer


def test_catalog_parses_api_payload() -> None:
    records = CardCatalog._parse_records(
        {
            "data": [
                {
                    "id": 14558127,
                    "name": "Ash Blossom & Joyous Spring",
                    "type": "Tuner Monster",
                    "frameType": "effect",
                    "card_images": [
                        {"image_url": "https://example.test/14558127.jpg"}
                    ],
                }
            ]
        }
    )

    assert records[14558127].name == "Ash Blossom & Joyous Spring"
    assert records[14558127].display_name == "Ash Blossom & Joyous Spring"
    assert records[14558127].frame_type == "effect"


def test_localizer_prefers_cached_master_duel_name(tmp_path) -> None:
    cache_path = tmp_path / "names.zh-Hans.json"
    cache_path.write_text(
        json.dumps(
            {
                "locale": "zh-Hans",
                "names": {"14558127": "灰流丽"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record = CardCatalog._parse_records(
        {
            "data": [
                {
                    "id": 14558127,
                    "name": "Ash Blossom & Joyous Spring",
                    "type": "Tuner Monster",
                    "frameType": "effect",
                    "card_images": [
                        {"image_url": "https://example.test/14558127.jpg"}
                    ],
                }
            ]
        }
    )[14558127]

    localized = CardNameLocalizer(cache_path).localize(
        [record],
        sync_missing=False,
    )

    assert localized[0].display_name == "灰流丽"


def test_localizer_parses_master_duel_name_before_other_names() -> None:
    names = CardNameLocalizer._parse_cardset_names(
        {
            "34761841": {
                "text": {
                    "name": "绯红共鸣者",
                    "sc_name": "深红共鸣者",
                    "md_name": "深红共鸣者",
                }
            }
        },
        (34761841,),
    )

    assert names == {34761841: "深红共鸣者"}

