from __future__ import annotations

import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable

from app.combos.loader import parse_combo_graph
from app.combos.models import ComboGraph
from app.deck_packs.models import DeckPack, DeckPackManifest, normalize_member_path
from app.decks.models import DeckList
from app.decks.ydk import parse_ydk


MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_MEMBER_SIZE = 16 * 1024 * 1024


def _referenced_card_ids(graph: ComboGraph) -> set[int]:
    card_ids: set[int] = set()
    for node in graph.nodes.values():
        card_ids.update(node.requirement.hand_contains)
        card_ids.update(node.requirement.field_contains)
        card_ids.update(node.requirement.graveyard_contains)
        card_ids.update(node.requirement.banished_contains)
    for edge in graph.edges:
        if edge.action.card_id is not None:
            card_ids.add(edge.action.card_id)
        if edge.action.target_card_id is not None:
            card_ids.add(edge.action.target_card_id)
    return card_ids


def _validate_pack_contents(
    manifest: DeckPackManifest, deck: DeckList, graph: ComboGraph
) -> None:
    for field_name, manifest_value, graph_value in (
        ("deck_pack_id", manifest.deck_pack_id, graph.deck_pack_id),
        ("version", manifest.version, graph.version),
        ("ruleset", manifest.ruleset, graph.ruleset),
        (
            "verification_status",
            manifest.verification_status,
            graph.verification_status,
        ),
    ):
        if manifest_value != graph_value:
            raise ValueError(
                f"Manifest {field_name} does not match graph: "
                f"{manifest_value!r} != {graph_value!r}"
            )

    missing_card_ids = sorted(_referenced_card_ids(graph) - set(deck.all_card_ids()))
    if missing_card_ids:
        raise ValueError(
            "Combo graph references cards outside the packaged deck: "
            f"{missing_card_ids}"
        )


def _assemble_pack(
    source_path: Path,
    read_text: Callable[[str, str], str],
) -> DeckPack:
    manifest_payload = json.loads(read_text("manifest.json", "utf-8-sig"))
    manifest = DeckPackManifest.from_dict(manifest_payload)
    deck = parse_ydk(
        read_text(manifest.deck_file, "utf-8-sig"),
        name=manifest.name,
    )
    graph = parse_combo_graph(
        json.loads(read_text(manifest.graph_file, "utf-8-sig"))
    )
    _validate_pack_contents(manifest, deck, graph)
    return DeckPack(
        manifest=manifest,
        deck=deck,
        graph=graph,
        source_path=source_path,
    )


def _directory_reader(root: Path) -> Callable[[str, str], str]:
    resolved_root = root.resolve()

    def read_text(member_name: str, encoding: str) -> str:
        normalized = normalize_member_path(member_name, field_name="pack member")
        target = resolved_root.joinpath(*PurePosixPath(normalized).parts).resolve()
        if target != resolved_root and resolved_root not in target.parents:
            raise ValueError(f"Deck pack member escapes its directory: {member_name}")
        if not target.is_file():
            raise ValueError(f"Deck pack is missing required file: {member_name}")
        if target.stat().st_size > MAX_MEMBER_SIZE:
            raise ValueError(f"Deck pack member is too large: {member_name}")
        return target.read_text(encoding=encoding)

    return read_text


def _load_archive(path: Path) -> DeckPack:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Invalid .ygopack archive: {path.name}") from exc

    with archive:
        members: dict[str, zipfile.ZipInfo] = {}
        total_size = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = normalize_member_path(info.filename, field_name="archive member")
            if name in members:
                raise ValueError(f"Duplicate file in deck pack: {name}")
            if info.flag_bits & 0x1:
                raise ValueError(f"Encrypted deck pack members are not supported: {name}")
            if info.file_size > MAX_MEMBER_SIZE:
                raise ValueError(f"Deck pack member is too large: {name}")
            total_size += info.file_size
            if total_size > MAX_ARCHIVE_SIZE:
                raise ValueError("Deck pack expands beyond the allowed size")
            members[name] = info

        def read_text(member_name: str, encoding: str) -> str:
            normalized = normalize_member_path(member_name, field_name="pack member")
            info = members.get(normalized)
            if info is None:
                raise ValueError(f"Deck pack is missing required file: {member_name}")
            try:
                return archive.read(info).decode(encoding)
            except UnicodeDecodeError as exc:
                raise ValueError(f"Deck pack file is not valid text: {member_name}") from exc

        return _assemble_pack(path, read_text)


def load_deck_pack(path: Path) -> DeckPack:
    path = path.resolve()
    if path.is_dir():
        return _assemble_pack(path, _directory_reader(path))
    if not path.is_file():
        raise ValueError(f"Deck pack does not exist: {path}")
    if path.suffix.casefold() != ".ygopack":
        raise ValueError("Deck packs must use the .ygopack extension")
    return _load_archive(path)


def build_deck_pack(source_directory: Path, output_path: Path) -> Path:
    source_directory = source_directory.resolve()
    if not source_directory.is_dir():
        raise ValueError(f"Deck pack source is not a directory: {source_directory}")
    load_deck_pack(source_directory)
    output_path = output_path.resolve()
    if output_path.suffix.casefold() != ".ygopack":
        raise ValueError("Deck pack output must use the .ygopack extension")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files = [
        path
        for path in source_directory.rglob("*")
        if path.is_file()
        and path.resolve() != output_path
        and path.suffix.casefold() != ".ygopack"
        and "__pycache__" not in path.parts
    ]
    files.sort(
        key=lambda path: (
            path.relative_to(source_directory).as_posix() != "manifest.json",
            path.relative_to(source_directory).as_posix(),
        )
    )

    with zipfile.ZipFile(
        output_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            archive.write(path, path.relative_to(source_directory).as_posix())

    load_deck_pack(output_path)
    return output_path
