from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app.authoring.card_resolver import CardNameResolver
from app.authoring.compiler import compile_combo_draft
from app.authoring.loader import load_combo_draft
from app.authoring.models import ComboDraft
from app.authoring.validator import validate_compiled_graph
from app.cards.catalog import CardCatalog, CardNameLocalizer
from app.combos.loader import save_combo_graph
from app.deck_packs.loader import build_deck_pack
from app.deck_packs.models import DeckPackManifest, SUPPORTED_FORMAT_VERSION
from app.decks.ydk import load_ydk


DEFAULT_CATALOG_PATH = Path("data/cards/catalog.json")
DEFAULT_NAMES_PATH = Path("data/cards/names.zh-Hans.json")


def create_deck_pack(
    ydk_path: Path,
    draft_path: Path,
    output_path: Path,
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    names_path: Path = DEFAULT_NAMES_PATH,
) -> Path:
    draft_path = draft_path.resolve()
    if not draft_path.is_file():
        raise ValueError(f"Combo draft does not exist: {draft_path}")
    return create_deck_pack_from_draft(
        ydk_path,
        load_combo_draft(draft_path),
        output_path,
        catalog_path=catalog_path,
        names_path=names_path,
    )


def create_deck_pack_from_draft(
    ydk_path: Path,
    draft: ComboDraft,
    output_path: Path,
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    names_path: Path = DEFAULT_NAMES_PATH,
) -> Path:
    ydk_path = ydk_path.resolve()
    output_path = output_path.resolve()
    if not ydk_path.is_file():
        raise ValueError(f"YDK file does not exist: {ydk_path}")

    deck = load_ydk(ydk_path)
    catalog = CardCatalog(catalog_path.resolve())
    catalog.ensure_loaded()
    localizer = CardNameLocalizer(names_path.resolve())
    resolver = CardNameResolver(deck, catalog, localizer)
    graph = compile_combo_draft(draft, deck, resolver)
    validate_compiled_graph(graph, deck)
    cover_card_id = (
        resolver.resolve(draft.cover_card, context="cover_card")
        if draft.cover_card is not None
        else None
    )

    manifest = DeckPackManifest(
        format_version=SUPPORTED_FORMAT_VERSION,
        deck_pack_id=draft.deck_pack_id,
        name=draft.name,
        version=draft.version,
        ruleset=draft.ruleset,
        verification_status=draft.verification_status,
        deck_file="deck.ydk",
        graph_file="graph.json",
        language=draft.language,
        author=draft.author,
        cover_card_id=cover_card_id,
        min_app_version=draft.min_app_version,
        notes=draft.notes,
    )
    manifest.validate()

    with tempfile.TemporaryDirectory(prefix="ygo-pack-authoring-") as temporary:
        root = Path(temporary)
        (root / manifest.deck_file).write_text(
            ydk_path.read_text(encoding="utf-8-sig"),
            encoding="utf-8",
        )
        save_combo_graph(graph, root / manifest.graph_file)
        manifest_payload = {
            "format_version": manifest.format_version,
            "deck_pack_id": manifest.deck_pack_id,
            "name": manifest.name,
            "author": manifest.author,
            "version": manifest.version,
            "ruleset": manifest.ruleset,
            "game": manifest.game,
            "language": manifest.language,
            "verification_status": manifest.verification_status,
            "deck_file": manifest.deck_file,
            "graph_file": manifest.graph_file,
            "cover_card_id": manifest.cover_card_id,
            "min_app_version": manifest.min_app_version,
            "notes": list(manifest.notes),
        }
        manifest_payload = {
            key: value
            for key, value in manifest_payload.items()
            if value not in (None, "", [])
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return build_deck_pack(root, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a .ygopack from a YDK and an AI-friendly combo draft"
    )
    parser.add_argument("--ydk", required=True, type=Path, help="Input .ydk file")
    parser.add_argument("--draft", required=True, type=Path, help="Input combo draft JSON")
    parser.add_argument("--output", type=Path, help="Output .ygopack path")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--names", type=Path, default=DEFAULT_NAMES_PATH)
    args = parser.parse_args()

    try:
        draft = load_combo_draft(args.draft)
        output = args.output or Path(f"{draft.deck_pack_id}-{draft.version}.ygopack")
        built_path = create_deck_pack(
            args.ydk,
            args.draft,
            output,
            catalog_path=args.catalog,
            names_path=args.names,
        )
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Built {built_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
