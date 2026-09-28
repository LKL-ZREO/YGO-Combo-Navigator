from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.combos.models import (
    ActionInstruction,
    ComboEdge,
    ComboGraph,
    ComboNode,
    RouteResult,
    StateRequirement,
)
from app.state.models import Phase, UsageState


def _card_counts(payload: dict | None) -> dict[int, int]:
    return {int(card_id): int(count) for card_id, count in (payload or {}).items()}


def parse_combo_graph(payload: dict) -> ComboGraph:
    nodes: dict[str, ComboNode] = {}

    for node_payload in payload["nodes"]:
        requirement_payload = node_payload.get("required_state", {})
        normal_summon_value = requirement_payload.get("normal_summon")
        requirement = StateRequirement(
            hand_contains=_card_counts(requirement_payload.get("hand_contains")),
            field_contains=_card_counts(requirement_payload.get("field_contains")),
            graveyard_contains=_card_counts(requirement_payload.get("graveyard_contains")),
            banished_contains=_card_counts(requirement_payload.get("banished_contains")),
            normal_summon=(UsageState(normal_summon_value) if normal_summon_value else None),
            effects_not_used=tuple(requirement_payload.get("effects_not_used", [])),
            effects_used=tuple(requirement_payload.get("effects_used", [])),
            forbidden_restrictions=tuple(
                requirement_payload.get("forbidden_restrictions", [])
            ),
            required_restrictions=tuple(
                requirement_payload.get("required_restrictions", [])
            ),
            allowed_phases=tuple(
                Phase(value)
                for value in requirement_payload.get(
                    "allowed_phases", ["MAIN1", "MAIN2", "UNKNOWN"]
                )
            ),
        )
        result_payload = node_payload.get("result")
        result = RouteResult(**result_payload) if result_payload else None
        node = ComboNode(
            node_id=node_payload["node_id"],
            name=node_payload.get("name", node_payload["node_id"]),
            requirement=requirement,
            result=result,
        )
        nodes[node.node_id] = node

    edges = tuple(
        ComboEdge(
            edge_id=edge_payload["edge_id"],
            from_node_id=edge_payload["from_node_id"],
            to_node_id=edge_payload["to_node_id"],
            action=ActionInstruction(**edge_payload["action"]),
            outcome=edge_payload.get("outcome", "SUCCEEDED"),
        )
        for edge_payload in payload.get("edges", [])
    )
    graph = ComboGraph(
        deck_pack_id=payload["deck_pack_id"],
        version=payload["version"],
        ruleset=payload["ruleset"],
        verification_status=payload.get("verification_status", "DRAFT"),
        sources=tuple(payload.get("sources", [])),
        nodes=nodes,
        edges=edges,
    )
    graph.validate()
    return graph


def load_combo_graph(path: Path) -> ComboGraph:
    return parse_combo_graph(json.loads(path.read_text(encoding="utf-8")))


def combo_graph_to_dict(graph: ComboGraph) -> dict:
    graph.validate()
    nodes: list[dict] = []
    for node in graph.nodes.values():
        requirement = node.requirement
        required_state: dict[str, object] = {}
        if requirement.hand_contains:
            required_state["hand_contains"] = {
                str(card_id): count
                for card_id, count in sorted(requirement.hand_contains.items())
            }
        if requirement.field_contains:
            required_state["field_contains"] = {
                str(card_id): count
                for card_id, count in sorted(requirement.field_contains.items())
            }
        if requirement.graveyard_contains:
            required_state["graveyard_contains"] = {
                str(card_id): count
                for card_id, count in sorted(requirement.graveyard_contains.items())
            }
        if requirement.banished_contains:
            required_state["banished_contains"] = {
                str(card_id): count
                for card_id, count in sorted(requirement.banished_contains.items())
            }
        if requirement.normal_summon is not None:
            required_state["normal_summon"] = requirement.normal_summon.value
        if requirement.effects_not_used:
            required_state["effects_not_used"] = list(requirement.effects_not_used)
        if requirement.effects_used:
            required_state["effects_used"] = list(requirement.effects_used)
        if requirement.forbidden_restrictions:
            required_state["forbidden_restrictions"] = list(
                requirement.forbidden_restrictions
            )
        if requirement.required_restrictions:
            required_state["required_restrictions"] = list(
                requirement.required_restrictions
            )
        required_state["allowed_phases"] = [
            phase.value for phase in requirement.allowed_phases
        ]
        node_payload: dict[str, object] = {
            "node_id": node.node_id,
            "name": node.name,
            "required_state": required_state,
        }
        if node.result is not None:
            node_payload["result"] = asdict(node.result)
        nodes.append(node_payload)

    edges = []
    for edge in graph.edges:
        action = asdict(edge.action)
        action = {key: value for key, value in action.items() if value is not None}
        edges.append(
            {
                "edge_id": edge.edge_id,
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "action": action,
                "outcome": edge.outcome,
            }
        )
    return {
        "deck_pack_id": graph.deck_pack_id,
        "version": graph.version,
        "ruleset": graph.ruleset,
        "verification_status": graph.verification_status,
        "sources": list(graph.sources),
        "nodes": nodes,
        "edges": edges,
    }


def save_combo_graph(graph: ComboGraph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(combo_graph_to_dict(graph), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

