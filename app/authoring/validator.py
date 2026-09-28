from __future__ import annotations

from app.combos.models import ComboGraph
from app.decks.models import DeckList


def referenced_card_ids(graph: ComboGraph) -> set[int]:
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


def validate_compiled_graph(graph: ComboGraph, deck: DeckList) -> None:
    graph.validate()
    if not graph.edges:
        raise ValueError("Compiled combo graph contains no actions")
    if not any(node.result is not None for node in graph.nodes.values()):
        raise ValueError("Compiled combo graph contains no terminal results")
    missing = sorted(referenced_card_ids(graph) - set(deck.all_card_ids()))
    if missing:
        raise ValueError(f"Compiled combo graph references cards outside the YDK: {missing}")
    reachable: set[str] = set()
    destinations = {edge.to_node_id for edge in graph.edges}
    roots = [node_id for node_id in graph.nodes if node_id not in destinations]
    pending = list(roots)
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(edge.to_node_id for edge in graph.outgoing(node_id))
    unreachable = sorted(set(graph.nodes) - reachable)
    if unreachable:
        raise ValueError(f"Compiled combo graph contains unreachable nodes: {unreachable}")
