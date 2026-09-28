import json
from pathlib import Path

import pytest

from app.authoring.card_resolver import CardNameResolver
from app.authoring.compiler import compile_combo_draft
from app.authoring.loader import parse_combo_draft
from app.cards.catalog import CardCatalog, CardNameLocalizer
from app.decks.ydk import parse_ydk
from app.tools.create_deck_pack import create_deck_pack
from app.tools.validate_deck_pack import validate


def _write_card_data(root: Path) -> tuple[Path, Path]:
    catalog_path = root / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "id": 1001,
                        "name": "Alpha Dragon",
                        "type": "Effect Monster",
                        "frameType": "effect",
                        "card_images": [{"image_url": "https://example.test/1001.jpg"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    names_path = root / "names.json"
    names_path.write_text(
        json.dumps({"locale": "zh-Hans", "names": {"1001": "阿尔法龙"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return catalog_path, names_path


def _draft_payload() -> dict:
    return {
        "deck_pack_id": "alpha-demo",
        "name": "Alpha Demo",
        "version": "0.1.0",
        "ruleset": "TEST",
        "routes": [
            {
                "route_id": "alpha-start",
                "name": "Alpha Start",
                "starting_hand": ["阿尔法龙"],
                "steps": [
                    {
                        "action": "NORMAL_SUMMON",
                        "card": "Alpha Dragon",
                        "instruction": "Normal Summon Alpha Dragon.",
                        "changes": {
                            "hand_remove": ["阿尔法龙"],
                            "field_add": ["Alpha Dragon"],
                            "normal_summon": "USED",
                        },
                    }
                ],
                "end_board": ["阿尔法龙"],
                "result": {
                    "end_board_score": 10,
                    "remaining_resource_score": 10,
                    "follow_up_score": 10,
                    "resilience_score": 10,
                    "summary": "Test route",
                },
            }
        ],
    }


def test_compiler_resolves_chinese_and_english_names(tmp_path: Path) -> None:
    catalog_path, names_path = _write_card_data(tmp_path)
    deck = parse_ydk("#main\n1001\n#extra\n")
    resolver = CardNameResolver(
        deck,
        CardCatalog(catalog_path),
        CardNameLocalizer(names_path),
    )

    graph = compile_combo_draft(parse_combo_draft(_draft_payload()), deck, resolver)

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert graph.edges[0].action.card_id == 1001
    assert graph.nodes["n0002"].requirement.field_contains == {1001: 1}


def test_draft_rejects_misspelled_fields() -> None:
    payload = _draft_payload()
    payload["routes"][0]["steps"][0]["change"] = {}

    with pytest.raises(ValueError, match="unsupported fields"):
        parse_combo_draft(payload)


def test_create_deck_pack_builds_loadable_archive(tmp_path: Path) -> None:
    catalog_path, names_path = _write_card_data(tmp_path)
    ydk_path = tmp_path / "alpha.ydk"
    ydk_path.write_text("#main\n1001\n#extra\n", encoding="utf-8")
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(
        json.dumps(_draft_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    output_path = tmp_path / "alpha-demo.ygopack"

    create_deck_pack(
        ydk_path,
        draft_path,
        output_path,
        catalog_path=catalog_path,
        names_path=names_path,
    )

    assert output_path.is_file()
    assert "2 nodes" in validate(output_path)
