from __future__ import annotations

from dataclasses import dataclass

from app.authoring.card_resolver import CardNameResolver
from app.authoring.compiler import compile_combo_draft
from app.authoring.loader import parse_combo_draft
from app.authoring.models import ComboDraft
from app.authoring.prompting import build_repair_prompt
from app.authoring.providers import DraftProvider
from app.authoring.validator import validate_compiled_graph
from app.decks.models import DeckList


@dataclass(frozen=True, slots=True)
class GeneratedDraft:
    draft: ComboDraft
    payload: object
    attempts: int


def validate_generated_payload(
    payload: object,
    deck: DeckList,
    resolver: CardNameResolver,
    *,
    expected_metadata: dict[str, object] | None = None,
) -> ComboDraft:
    draft = parse_combo_draft(payload)
    if expected_metadata:
        for field_name, expected_value in expected_metadata.items():
            actual_value = getattr(draft, field_name)
            if actual_value != expected_value:
                raise ValueError(
                    f"AI changed required metadata {field_name}: "
                    f"{actual_value!r} != {expected_value!r}"
                )
    if draft.cover_card is not None:
        resolver.resolve(draft.cover_card, context="cover_card")
    graph = compile_combo_draft(draft, deck, resolver)
    validate_compiled_graph(graph, deck)
    return draft


def generate_validated_draft(
    provider: DraftProvider,
    *,
    prompt: str,
    schema: dict,
    deck: DeckList,
    resolver: CardNameResolver,
    max_attempts: int = 3,
    expected_metadata: dict[str, object] | None = None,
) -> GeneratedDraft:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    current_prompt = prompt
    last_error: ValueError | None = None
    for attempt in range(1, max_attempts + 1):
        payload = provider.generate(current_prompt, schema)
        try:
            draft = validate_generated_payload(
                payload,
                deck,
                resolver,
                expected_metadata=expected_metadata,
            )
        except (KeyError, ValueError) as exc:
            last_error = ValueError(str(exc))
            if attempt == max_attempts:
                break
            current_prompt = build_repair_prompt(prompt, payload, str(exc))
            continue
        return GeneratedDraft(draft=draft, payload=payload, attempts=attempt)
    raise ValueError(
        f"AI could not produce a compilable ComboDraft after {max_attempts} attempts: {last_error}"
    )
