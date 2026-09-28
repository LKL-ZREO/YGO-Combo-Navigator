from __future__ import annotations

from pathlib import Path

from app.decks.models import DeckList


SECTION_MARKERS = {"#main": "main", "#extra": "extra", "!side": "side"}


def parse_ydk(text: str, *, name: str = "Imported Deck") -> DeckList:
    sections: dict[str, list[int]] = {"main": [], "extra": [], "side": []}
    current_section: str | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("//"):
            continue
        lowered = line.casefold()
        if lowered in SECTION_MARKERS:
            current_section = SECTION_MARKERS[lowered]
            continue
        if line.startswith("#") or line.startswith("!"):
            continue
        if current_section is None:
            raise ValueError(f"Card ID appears before a section marker on line {line_number}")
        try:
            card_id = int(line)
        except ValueError as exc:
            raise ValueError(f"Invalid card ID on line {line_number}: {line}") from exc
        if card_id <= 0:
            raise ValueError(f"Invalid card ID on line {line_number}: {line}")
        sections[current_section].append(card_id)

    deck = DeckList(
        name=name,
        main=tuple(sections["main"]),
        extra=tuple(sections["extra"]),
        side=tuple(sections["side"]),
    )
    deck.validate()
    if not deck.main and not deck.extra:
        raise ValueError("The .ydk file contains no Main or Extra Deck cards")
    return deck


def load_ydk(path: Path) -> DeckList:
    return parse_ydk(path.read_text(encoding="utf-8-sig"), name=path.stem)

