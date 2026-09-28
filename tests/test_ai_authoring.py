import json
from pathlib import Path

import pytest

from app.authoring.card_resolver import CardNameResolver
from app.authoring.generation import generate_validated_draft
from app.authoring.prompting import build_authoring_prompt, build_deck_inventory
from app.authoring.providers import OpenAIResponsesProvider, parse_json_response
from app.authoring.source_loader import GuideSource, html_to_text, validate_public_url
from app.cards.catalog import CardCatalog, CardNameLocalizer
from app.decks.ydk import parse_ydk


def _card_services(root: Path):
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
        json.dumps({"names": {"1001": "阿尔法龙"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return CardCatalog(catalog_path), CardNameLocalizer(names_path)


def _valid_payload() -> dict:
    return {
        "deck_pack_id": "alpha-demo",
        "name": "Alpha Demo",
        "version": "0.1.0",
        "ruleset": "MD_2026_09_28",
        "verification_status": "DRAFT",
        "author": "Tester",
        "language": "zh-Hans",
        "sources": ["guide.txt"],
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


def test_html_guide_extraction_ignores_scripts() -> None:
    text = html_to_text(
        "<html><body><h1>Combo</h1><script>ignore me</script><p>Summon Alpha.</p></body></html>"
    )

    assert "Combo" in text
    assert "Summon Alpha." in text
    assert "ignore me" not in text


def test_guide_url_rejects_loopback() -> None:
    with pytest.raises(ValueError, match="private or unsafe"):
        validate_public_url("http://127.0.0.1/guide")


def test_prompt_contains_names_but_not_card_ids(tmp_path: Path) -> None:
    catalog, localizer = _card_services(tmp_path)
    deck = parse_ydk("#main\n1001\n#extra\n")
    inventory = build_deck_inventory(deck, catalog, localizer)
    prompt = build_authoring_prompt(
        deck_inventory=inventory,
        guide=GuideSource(label="guide.txt", text="Normal Summon Alpha Dragon."),
        deck_pack_id="alpha-demo",
        name="Alpha Demo",
        version="0.1.0",
        ruleset="MD_2026_09_28",
    )

    assert "阿尔法龙 / Alpha Dragon x1" in prompt
    assert "1001" not in prompt


def test_generation_repairs_invalid_first_response(tmp_path: Path) -> None:
    catalog, localizer = _card_services(tmp_path)
    deck = parse_ydk("#main\n1001\n#extra\n")
    resolver = CardNameResolver(deck, catalog, localizer)
    valid = _valid_payload()
    invalid = json.loads(json.dumps(valid, ensure_ascii=False))
    invalid["routes"][0]["starting_hand"] = ["Missing Card"]

    class FakeProvider:
        def __init__(self) -> None:
            self.responses = [invalid, valid]
            self.prompts: list[str] = []

        def generate(self, prompt: str, schema: dict) -> object:
            self.prompts.append(prompt)
            return self.responses.pop(0)

    provider = FakeProvider()
    generated = generate_validated_draft(
        provider,
        prompt="original prompt",
        schema={},
        deck=deck,
        resolver=resolver,
        max_attempts=2,
        expected_metadata={
            "deck_pack_id": "alpha-demo",
            "name": "Alpha Demo",
            "version": "0.1.0",
            "ruleset": "MD_2026_09_28",
            "verification_status": "DRAFT",
            "author": "Tester",
            "language": "zh-Hans",
            "sources": ("guide.txt",),
        },
    )

    assert generated.attempts == 2
    assert "Compiler error" in provider.prompts[1]
    assert generated.draft.deck_pack_id == "alpha-demo"


def test_openai_response_text_and_fenced_json_are_parsed() -> None:
    payload = {"output": [{"content": [{"type": "output_text", "text": "{\"ok\": true}"}]}]}
    text = OpenAIResponsesProvider._output_text(payload)
    fenced = f"{chr(96) * 3}json\n{text}\n{chr(96) * 3}"

    assert parse_json_response(fenced) == {"ok": True}
