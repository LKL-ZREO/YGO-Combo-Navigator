from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.combos.loader import load_combo_graph
from app.combos.models import ComboGraph
from app.deck_packs.loader import load_deck_pack
from app.decks.ydk import load_ydk


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


def validate(path: Path) -> str:
    if path.suffix.casefold() == ".ygopack":
        pack = load_deck_pack(path)
        graph = pack.graph
        terminal_count = sum(node.result is not None for node in graph.nodes.values())
        return (
            f"OK: {pack.manifest.deck_pack_id} {pack.manifest.version} | "
            f"{len(graph.nodes)} nodes | {len(graph.edges)} edges | "
            f"{terminal_count} results | {pack.manifest.verification_status} | "
            f"deck {len(pack.deck.main)} main/{len(pack.deck.extra)} extra/"
            f"{len(pack.deck.side)} side"
        )

    graph_path = path / "graph.json" if path.is_dir() else path
    graph = load_combo_graph(graph_path)
    terminal_count = sum(node.result is not None for node in graph.nodes.values())
    if terminal_count == 0:
        raise ValueError("Deck pack contains no terminal result nodes")
    if not graph.edges:
        raise ValueError("Deck pack contains no actions")
    summary = (
        f"OK: {graph.deck_pack_id} {graph.version} | "
        f"{len(graph.nodes)} nodes | {len(graph.edges)} edges | "
        f"{terminal_count} results | {graph.verification_status}"
    )

    if path.is_dir() and (path / "manifest.json").exists():
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        for field, graph_value in (
            ("deck_pack_id", graph.deck_pack_id),
            ("version", graph.version),
            ("ruleset", graph.ruleset),
            ("verification_status", graph.verification_status),
        ):
            if manifest.get(field) != graph_value:
                raise ValueError(
                    f"Manifest {field} does not match graph: "
                    f"{manifest.get(field)!r} != {graph_value!r}"
                )

        deck_filename = manifest.get("deck_file")
        if deck_filename:
            deck = load_ydk(path / deck_filename)
            missing_card_ids = sorted(
                _referenced_card_ids(graph) - set(deck.all_card_ids())
            )
            if missing_card_ids:
                raise ValueError(
                    f"Combo graph references cards outside {deck_filename}: "
                    f"{missing_card_ids}"
                )
            summary += (
                f" | deck {len(deck.main)} main/"
                f"{len(deck.extra)} extra/{len(deck.side)} side"
            )

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a combo deck pack")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(validate(args.path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

