from __future__ import annotations

import re
from dataclasses import dataclass

from app.authoring.action_types import DraftActionType
from app.deck_packs.models import VERIFICATION_STATUSES
from app.state.models import UsageState


_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _reject_unknown(
    payload: dict,
    supported: set[str],
    *,
    field_name: str,
) -> None:
    unknown = sorted(set(payload) - supported)
    if unknown:
        raise ValueError(f"{field_name} has unsupported fields: {unknown}")


def _text(value: object, *, field_name: str, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    result = value.strip()
    if required and not result:
        raise ValueError(f"{field_name} cannot be empty")
    return result


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return tuple(
        _text(item, field_name=f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )


def _score(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    result = float(value)
    if not 0 <= result <= 100:
        raise ValueError(f"{field_name} must be between 0 and 100")
    return result


@dataclass(frozen=True, slots=True)
class DraftStateChanges:
    hand_add: tuple[str, ...] = ()
    hand_remove: tuple[str, ...] = ()
    field_add: tuple[str, ...] = ()
    field_remove: tuple[str, ...] = ()
    graveyard_add: tuple[str, ...] = ()
    graveyard_remove: tuple[str, ...] = ()
    banished_add: tuple[str, ...] = ()
    banished_remove: tuple[str, ...] = ()
    normal_summon: UsageState | None = None
    effects_used: tuple[str, ...] = ()
    restrictions_add: tuple[str, ...] = ()
    restrictions_remove: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: object, *, field_name: str) -> "DraftStateChanges":
        if not isinstance(payload, dict):
            raise ValueError(f"{field_name} must be an object")
        supported = {
            "hand_add",
            "hand_remove",
            "field_add",
            "field_remove",
            "graveyard_add",
            "graveyard_remove",
            "banished_add",
            "banished_remove",
            "normal_summon",
            "effects_used",
            "restrictions_add",
            "restrictions_remove",
        }
        _reject_unknown(payload, supported, field_name=field_name)
        normal_summon_value = payload.get("normal_summon")
        try:
            normal_summon = (
                UsageState(str(normal_summon_value))
                if normal_summon_value is not None
                else None
            )
        except ValueError as exc:
            raise ValueError(
                f"{field_name}.normal_summon must be AVAILABLE, USED, or UNKNOWN"
            ) from exc
        return cls(
            hand_add=_string_tuple(payload.get("hand_add"), field_name=f"{field_name}.hand_add"),
            hand_remove=_string_tuple(payload.get("hand_remove"), field_name=f"{field_name}.hand_remove"),
            field_add=_string_tuple(payload.get("field_add"), field_name=f"{field_name}.field_add"),
            field_remove=_string_tuple(payload.get("field_remove"), field_name=f"{field_name}.field_remove"),
            graveyard_add=_string_tuple(payload.get("graveyard_add"), field_name=f"{field_name}.graveyard_add"),
            graveyard_remove=_string_tuple(payload.get("graveyard_remove"), field_name=f"{field_name}.graveyard_remove"),
            banished_add=_string_tuple(payload.get("banished_add"), field_name=f"{field_name}.banished_add"),
            banished_remove=_string_tuple(payload.get("banished_remove"), field_name=f"{field_name}.banished_remove"),
            normal_summon=normal_summon,
            effects_used=_string_tuple(payload.get("effects_used"), field_name=f"{field_name}.effects_used"),
            restrictions_add=_string_tuple(payload.get("restrictions_add"), field_name=f"{field_name}.restrictions_add"),
            restrictions_remove=_string_tuple(payload.get("restrictions_remove"), field_name=f"{field_name}.restrictions_remove"),
        )


@dataclass(frozen=True, slots=True)
class DraftStep:
    action: DraftActionType
    instruction: str
    changes: DraftStateChanges
    card: str | None = None
    target_card: str | None = None
    effect_id: str | None = None

    @classmethod
    def from_dict(cls, payload: object, *, field_name: str) -> "DraftStep":
        if not isinstance(payload, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            payload,
            {"action", "card", "target_card", "effect_id", "instruction", "changes"},
            field_name=field_name,
        )
        if "changes" not in payload:
            raise ValueError(f"{field_name}.changes is required")
        try:
            action = DraftActionType(_text(payload.get("action"), field_name=f"{field_name}.action"))
        except ValueError as exc:
            raise ValueError(f"{field_name}.action is unsupported: {payload.get('action')!r}") from exc
        card_value = payload.get("card")
        target_value = payload.get("target_card")
        effect_value = payload.get("effect_id")
        return cls(
            action=action,
            card=(
                _text(card_value, field_name=f"{field_name}.card")
                if card_value is not None
                else None
            ),
            target_card=(
                _text(target_value, field_name=f"{field_name}.target_card")
                if target_value is not None
                else None
            ),
            effect_id=(
                _text(effect_value, field_name=f"{field_name}.effect_id")
                if effect_value is not None
                else None
            ),
            instruction=_text(payload.get("instruction"), field_name=f"{field_name}.instruction"),
            changes=DraftStateChanges.from_dict(
                payload.get("changes", {}), field_name=f"{field_name}.changes"
            ),
        )


@dataclass(frozen=True, slots=True)
class DraftRouteResult:
    end_board_score: float
    remaining_resource_score: float
    follow_up_score: float
    resilience_score: float
    summary: str

    @classmethod
    def from_dict(cls, payload: object, *, field_name: str) -> "DraftRouteResult":
        if not isinstance(payload, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            payload,
            {
                "end_board_score",
                "remaining_resource_score",
                "follow_up_score",
                "resilience_score",
                "summary",
            },
            field_name=field_name,
        )
        return cls(
            end_board_score=_score(payload.get("end_board_score"), field_name=f"{field_name}.end_board_score"),
            remaining_resource_score=_score(payload.get("remaining_resource_score"), field_name=f"{field_name}.remaining_resource_score"),
            follow_up_score=_score(payload.get("follow_up_score"), field_name=f"{field_name}.follow_up_score"),
            resilience_score=_score(payload.get("resilience_score"), field_name=f"{field_name}.resilience_score"),
            summary=_text(payload.get("summary", ""), field_name=f"{field_name}.summary", required=False),
        )


@dataclass(frozen=True, slots=True)
class DraftRoute:
    route_id: str
    name: str
    starting_hand: tuple[str, ...]
    starting_field: tuple[str, ...]
    starting_graveyard: tuple[str, ...]
    starting_banished: tuple[str, ...]
    normal_summon: UsageState
    steps: tuple[DraftStep, ...]
    end_board: tuple[str, ...]
    result: DraftRouteResult

    @classmethod
    def from_dict(cls, payload: object, *, index: int) -> "DraftRoute":
        field_name = f"routes[{index}]"
        if not isinstance(payload, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            payload,
            {
                "route_id",
                "name",
                "starting_hand",
                "starting_field",
                "starting_graveyard",
                "starting_banished",
                "normal_summon",
                "steps",
                "end_board",
                "result",
            },
            field_name=field_name,
        )
        for required_field in ("starting_hand", "end_board", "result"):
            if required_field not in payload:
                raise ValueError(f"{field_name}.{required_field} is required")
        route_id = _text(payload.get("route_id"), field_name=f"{field_name}.route_id")
        if not _IDENTIFIER_PATTERN.fullmatch(route_id):
            raise ValueError(f"{field_name}.route_id must use lowercase letters, digits, '.', '_', or '-'")
        steps_payload = payload.get("steps")
        if not isinstance(steps_payload, list) or not steps_payload:
            raise ValueError(f"{field_name}.steps must be a non-empty list")
        try:
            normal_summon = UsageState(str(payload.get("normal_summon", "AVAILABLE")))
        except ValueError as exc:
            raise ValueError(f"{field_name}.normal_summon is invalid") from exc
        return cls(
            route_id=route_id,
            name=_text(payload.get("name"), field_name=f"{field_name}.name"),
            starting_hand=_string_tuple(payload.get("starting_hand"), field_name=f"{field_name}.starting_hand"),
            starting_field=_string_tuple(payload.get("starting_field"), field_name=f"{field_name}.starting_field"),
            starting_graveyard=_string_tuple(payload.get("starting_graveyard"), field_name=f"{field_name}.starting_graveyard"),
            starting_banished=_string_tuple(payload.get("starting_banished"), field_name=f"{field_name}.starting_banished"),
            normal_summon=normal_summon,
            steps=tuple(
                DraftStep.from_dict(item, field_name=f"{field_name}.steps[{step_index}]")
                for step_index, item in enumerate(steps_payload)
            ),
            end_board=_string_tuple(payload.get("end_board"), field_name=f"{field_name}.end_board"),
            result=DraftRouteResult.from_dict(payload.get("result"), field_name=f"{field_name}.result"),
        )


@dataclass(frozen=True, slots=True)
class ComboDraft:
    deck_pack_id: str
    name: str
    version: str
    ruleset: str
    verification_status: str
    sources: tuple[str, ...]
    routes: tuple[DraftRoute, ...]
    author: str = ""
    language: str = "zh-Hans"
    notes: tuple[str, ...] = ()
    cover_card: str | None = None
    min_app_version: str | None = "0.2.0"

    @classmethod
    def from_dict(cls, payload: object) -> "ComboDraft":
        if not isinstance(payload, dict):
            raise ValueError("Combo draft must be a JSON object")
        _reject_unknown(
            payload,
            {
                "deck_pack_id",
                "name",
                "version",
                "ruleset",
                "verification_status",
                "sources",
                "routes",
                "author",
                "language",
                "notes",
                "cover_card",
                "min_app_version",
            },
            field_name="combo draft",
        )
        deck_pack_id = _text(payload.get("deck_pack_id"), field_name="deck_pack_id")
        if not _IDENTIFIER_PATTERN.fullmatch(deck_pack_id):
            raise ValueError("deck_pack_id must use lowercase letters, digits, '.', '_', or '-'")
        verification_status = _text(
            payload.get("verification_status", "DRAFT"),
            field_name="verification_status",
        )
        if verification_status not in VERIFICATION_STATUSES:
            raise ValueError(f"Unsupported verification_status: {verification_status}")
        routes_payload = payload.get("routes")
        if not isinstance(routes_payload, list) or not routes_payload:
            raise ValueError("routes must be a non-empty list")
        routes = tuple(
            DraftRoute.from_dict(item, index=index)
            for index, item in enumerate(routes_payload)
        )
        route_ids = [route.route_id for route in routes]
        duplicates = sorted({value for value in route_ids if route_ids.count(value) > 1})
        if duplicates:
            raise ValueError(f"Duplicate route_id values: {duplicates}")
        cover_value = payload.get("cover_card")
        min_version_value = payload.get("min_app_version", "0.2.0")
        return cls(
            deck_pack_id=deck_pack_id,
            name=_text(payload.get("name"), field_name="name"),
            version=_text(payload.get("version"), field_name="version"),
            ruleset=_text(payload.get("ruleset"), field_name="ruleset"),
            verification_status=verification_status,
            sources=_string_tuple(payload.get("sources"), field_name="sources"),
            routes=routes,
            author=_text(payload.get("author", ""), field_name="author", required=False),
            language=_text(payload.get("language", "zh-Hans"), field_name="language"),
            notes=_string_tuple(payload.get("notes"), field_name="notes"),
            cover_card=(
                _text(cover_value, field_name="cover_card")
                if cover_value is not None
                else None
            ),
            min_app_version=(
                _text(min_version_value, field_name="min_app_version")
                if min_version_value is not None
                else None
            ),
        )
