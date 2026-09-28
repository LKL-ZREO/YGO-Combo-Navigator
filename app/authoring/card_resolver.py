from __future__ import annotations

import unicodedata
from collections import defaultdict

from app.cards.catalog import CardCatalog, CardNameLocalizer, CardRecord
from app.decks.models import DeckList


def normalize_card_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


class CardNameResolver:
    def __init__(
        self,
        deck: DeckList,
        catalog: CardCatalog,
        localizer: CardNameLocalizer,
    ) -> None:
        records = localizer.localize(
            catalog.get_many(deck.all_card_ids()),
            sync_missing=False,
        )
        self._records = {record.card_id: record for record in records}
        self._exact: dict[str, set[int]] = defaultdict(set)
        self._normalized: dict[str, set[int]] = defaultdict(set)
        for record in records:
            for name in self._record_names(record):
                self._exact[name.casefold()].add(record.card_id)
                normalized = normalize_card_name(name)
                if normalized:
                    self._normalized[normalized].add(record.card_id)

    @staticmethod
    def _record_names(record: CardRecord) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                name.strip()
                for name in (record.localized_name, record.name)
                if name and name.strip()
            )
        )

    def resolve(self, name: str, *, context: str = "card") -> int:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{context} must be a non-empty card name")
        query = name.strip()
        candidates = self._exact.get(query.casefold(), set())
        if not candidates:
            candidates = self._normalized.get(normalize_card_name(query), set())
        if not candidates:
            raise ValueError(
                f"{context} {query!r} was not found in the supplied YDK. "
                "Use the exact Chinese or English card name."
            )
        if len(candidates) > 1:
            choices = ", ".join(
                f"{self._records[card_id].display_name} ({card_id})"
                for card_id in sorted(candidates)
            )
            raise ValueError(
                f"{context} {query!r} is ambiguous inside the supplied YDK: {choices}"
            )
        return next(iter(candidates))
