from __future__ import annotations

from collections import Counter

from app.combos.models import (
    ComboGraph,
    RequirementMatch,
    RouteCandidate,
    RouteResult,
    StateRequirement,
)
from app.state.models import DuelState, UsageState


def _missing_cards(required: dict[int, int], actual: Counter[int]) -> list[str]:
    return [
        f"card:{card_id} requires {count}, has {actual[card_id]}"
        for card_id, count in required.items()
        if actual[card_id] < count
    ]


def match_requirement(requirement: StateRequirement, state: DuelState) -> RequirementMatch:
    failures = [
        *_missing_cards(requirement.hand_contains, state.hand),
        *_missing_cards(requirement.field_contains, state.field),
        *_missing_cards(requirement.graveyard_contains, state.known_graveyard),
        *_missing_cards(requirement.banished_contains, state.known_banished),
    ]
    unresolved: list[str] = []

    if state.phase not in requirement.allowed_phases:
        failures.append(f"phase:{state.phase}")

    if requirement.normal_summon is not None:
        if state.normal_summon == UsageState.UNKNOWN:
            unresolved.append("normal_summon")
        elif state.normal_summon != requirement.normal_summon:
            failures.append(
                f"normal_summon requires {requirement.normal_summon}, has {state.normal_summon}"
            )

    for effect_id in requirement.effects_not_used:
        usage = state.used_effects.get(effect_id, UsageState.UNKNOWN)
        if usage == UsageState.USED:
            failures.append(f"effect_used:{effect_id}")
        elif usage == UsageState.UNKNOWN:
            unresolved.append(f"effect_unknown:{effect_id}")

    for effect_id in requirement.effects_used:
        usage = state.used_effects.get(effect_id, UsageState.UNKNOWN)
        if usage == UsageState.AVAILABLE:
            failures.append(f"effect_not_used:{effect_id}")
        elif usage == UsageState.UNKNOWN:
            unresolved.append(f"effect_unknown:{effect_id}")

    for restriction in requirement.forbidden_restrictions:
        if restriction in state.active_restrictions:
            failures.append(f"active_restriction:{restriction}")

    for restriction in requirement.required_restrictions:
        if restriction not in state.active_restrictions:
            failures.append(f"missing_restriction:{restriction}")

    confidence = state.recognition_confidence * (0.84 ** len(unresolved))
    return RequirementMatch(
        matched=not failures,
        confidence=max(0.0, min(1.0, confidence)),
        unresolved=tuple(unresolved),
        failures=tuple(failures),
    )


class RouteMatcher:
    def __init__(self, *, max_steps: int = 20) -> None:
        self.max_steps = max_steps

    def match(
        self,
        state: DuelState,
        graph: ComboGraph,
        *,
        limit: int = 5,
    ) -> list[RouteCandidate]:
        candidates: list[RouteCandidate] = []
        for node in graph.nodes.values():
            requirement_match = match_requirement(node.requirement, state)
            if not requirement_match.matched:
                continue
            candidates.extend(
                self._walk_from(
                    graph,
                    node.node_id,
                    confidence=requirement_match.confidence,
                    unresolved=requirement_match.unresolved,
                    visited=(node.node_id,),
                )
            )

        unique: dict[tuple[str, tuple[str, ...]], RouteCandidate] = {}
        for candidate in candidates:
            key = (
                candidate.start_node_id,
                tuple(action.instruction for action in candidate.actions),
            )
            existing = unique.get(key)
            if existing is None or candidate.score > existing.score:
                unique[key] = candidate
        return sorted(unique.values(), key=lambda item: item.score, reverse=True)[:limit]

    def _walk_from(
        self,
        graph: ComboGraph,
        node_id: str,
        *,
        confidence: float,
        unresolved: tuple[str, ...],
        visited: tuple[str, ...],
    ) -> list[RouteCandidate]:
        node = graph.nodes[node_id]
        candidates: list[RouteCandidate] = []
        if node.result is not None:
            candidates.append(
                RouteCandidate(
                    start_node_id=node_id,
                    terminal_node_id=node_id,
                    node_path=(node_id,),
                    actions=(),
                    result=node.result,
                    score=self._score(node.result, confidence, len(unresolved), 0),
                    confidence=confidence,
                    unresolved_requirements=unresolved,
                )
            )
        if len(visited) > self.max_steps:
            return candidates

        for edge in graph.outgoing(node_id):
            if edge.outcome != "SUCCEEDED" or edge.to_node_id in visited:
                continue
            tails = self._walk_from(
                graph,
                edge.to_node_id,
                confidence=confidence,
                unresolved=unresolved,
                visited=(*visited, edge.to_node_id),
            )
            for tail in tails:
                actions = (edge.action, *tail.actions)
                candidates.append(
                    RouteCandidate(
                        start_node_id=node_id,
                        terminal_node_id=tail.terminal_node_id,
                        node_path=(node_id, *tail.node_path),
                        actions=actions,
                        result=tail.result,
                        score=self._score(
                            tail.result,
                            confidence,
                            len(unresolved),
                            len(actions),
                        ),
                        confidence=confidence,
                        unresolved_requirements=unresolved,
                    )
                )
        return candidates

    @staticmethod
    def _score(
        result: RouteResult,
        confidence: float,
        unresolved_count: int,
        action_count: int,
    ) -> float:
        value = (
            0.35 * result.end_board_score
            + 0.20 * result.remaining_resource_score
            + 0.20 * result.follow_up_score
            + 0.15 * result.resilience_score
            + 10.0 * confidence
            - 4.0 * unresolved_count
            - 0.15 * action_count
        )
        return round(value, 4)

