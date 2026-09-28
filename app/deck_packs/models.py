from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.combos.models import ComboGraph
from app.decks.models import DeckList


SUPPORTED_FORMAT_VERSION = 1
VERIFICATION_STATUSES = {"VERIFIED", "COMMUNITY_TRANSCRIBED", "DRAFT"}
_PACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def normalize_member_path(value: str, *, field_name: str) -> str:
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path == PurePosixPath(".")
        or path.is_absolute()
        or ".." in path.parts
        or (path.parts and ":" in path.parts[0])
        or any(part in {"", "."} for part in path.parts)
    ):
        raise ValueError(f"Invalid {field_name}: {value!r}")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class DeckPackManifest:
    format_version: int
    deck_pack_id: str
    name: str
    version: str
    ruleset: str
    verification_status: str
    deck_file: str
    graph_file: str
    game: str = "MASTER_DUEL"
    language: str = "zh-Hans"
    author: str = ""
    cover_card_id: int | None = None
    min_app_version: str | None = None
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict) -> "DeckPackManifest":
        if not isinstance(payload, dict):
            raise ValueError("Deck pack manifest must be a JSON object")
        notes_payload = payload.get("notes", [])
        if not isinstance(notes_payload, list):
            raise ValueError("Deck pack manifest notes must be a list")
        try:
            manifest = cls(
                format_version=int(payload["format_version"]),
                deck_pack_id=str(payload["deck_pack_id"]).strip(),
                name=str(payload["name"]).strip(),
                version=str(payload["version"]).strip(),
                ruleset=str(payload["ruleset"]).strip(),
                verification_status=str(payload["verification_status"]).strip(),
                deck_file=normalize_member_path(
                    str(payload["deck_file"]), field_name="deck_file"
                ),
                graph_file=normalize_member_path(
                    str(payload["graph_file"]), field_name="graph_file"
                ),
                game=str(payload.get("game", "MASTER_DUEL")).strip(),
                language=str(payload.get("language", "zh-Hans")).strip(),
                author=str(payload.get("author", "")).strip(),
                cover_card_id=(
                    int(payload["cover_card_id"])
                    if payload.get("cover_card_id") is not None
                    else None
                ),
                min_app_version=(
                    str(payload["min_app_version"]).strip()
                    if payload.get("min_app_version")
                    else None
                ),
                notes=tuple(str(note).strip() for note in notes_payload),
            )
        except KeyError as exc:
            raise ValueError(f"Deck pack manifest is missing {exc.args[0]}") from exc
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.format_version != SUPPORTED_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported deck pack format version: {self.format_version}"
            )
        if not _PACK_ID_PATTERN.fullmatch(self.deck_pack_id):
            raise ValueError(f"Invalid deck_pack_id: {self.deck_pack_id!r}")
        for field_name, value in (
            ("name", self.name),
            ("version", self.version),
            ("ruleset", self.ruleset),
            ("game", self.game),
            ("language", self.language),
        ):
            if not value:
                raise ValueError(f"Deck pack {field_name} cannot be empty")
        if self.verification_status not in VERIFICATION_STATUSES:
            raise ValueError(
                f"Unsupported verification status: {self.verification_status}"
            )
        if self.deck_file == self.graph_file:
            raise ValueError("deck_file and graph_file must be different files")
        if self.cover_card_id is not None and self.cover_card_id <= 0:
            raise ValueError("cover_card_id must be a positive card ID")


@dataclass(frozen=True, slots=True)
class DeckPack:
    manifest: DeckPackManifest
    deck: DeckList
    graph: ComboGraph
    source_path: Path
