from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DeckList:
    name: str
    main: tuple[int, ...]
    extra: tuple[int, ...]
    side: tuple[int, ...] = ()

    def all_card_ids(self) -> tuple[int, ...]:
        return tuple(dict.fromkeys((*self.main, *self.extra, *self.side)))

    def counts(self) -> Counter[int]:
        return Counter((*self.main, *self.extra, *self.side))

    def validate(self, *, enforce_tournament_sizes: bool = False) -> None:
        if not self.name.strip():
            raise ValueError("Deck name cannot be empty")
        if any(card_id <= 0 for card_id in (*self.main, *self.extra, *self.side)):
            raise ValueError("Card IDs must be positive integers")
        if len(self.extra) > 15:
            raise ValueError("Extra Deck cannot contain more than 15 cards")
        if len(self.side) > 15:
            raise ValueError("Side Deck cannot contain more than 15 cards")
        if enforce_tournament_sizes and not 40 <= len(self.main) <= 60:
            raise ValueError("Main Deck must contain 40 to 60 cards")

    def save(self, path: Path) -> None:
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["main"] = list(self.main)
        payload["extra"] = list(self.extra)
        payload["side"] = list(self.side)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "DeckList":
        payload = json.loads(path.read_text(encoding="utf-8"))
        deck = cls(
            name=payload["name"],
            main=tuple(int(value) for value in payload["main"]),
            extra=tuple(int(value) for value in payload["extra"]),
            side=tuple(int(value) for value in payload.get("side", [])),
        )
        deck.validate()
        return deck

