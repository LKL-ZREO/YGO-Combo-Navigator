from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field as dataclass_field

from app.authoring.card_resolver import CardNameResolver
from app.authoring.models import ComboDraft, DraftRoute, DraftStateChanges, DraftStep
from app.combos.models import (
    ActionInstruction,
    ComboEdge,
    ComboGraph,
    ComboNode,
    RouteResult,
    StateRequirement,
)
from app.decks.models import DeckList
from app.state.models import UsageState


@dataclass(slots=True)
class _CompileState:
    hand: Counter[int] = dataclass_field(default_factory=Counter)
    field: Counter[int] = dataclass_field(default_factory=Counter)
    graveyard: Counter[int] = dataclass_field(default_factory=Counter)
    banished: Counter[int] = dataclass_field(default_factory=Counter)
    normal_summon: UsageState = UsageState.AVAILABLE
    effects_used: set[str] = dataclass_field(default_factory=set)
    restrictions: set[str] = dataclass_field(default_factory=set)

    def copy(self) -> "_CompileState":
        return _CompileState(
            hand=self.hand.copy(),
            field=self.field.copy(),
            graveyard=self.graveyard.copy(),
            banished=self.banished.copy(),
            normal_summon=self.normal_summon,
            effects_used=set(self.effects_used),
            restrictions=set(self.restrictions),
        )

    def signature(self) -> tuple:
        def counts(counter: Counter[int]) -> tuple[tuple[int, int], ...]:
            return tuple(sorted((card_id, count) for card_id, count in counter.items() if count))

        return (
            counts(self.hand),
            counts(self.field),
            counts(self.graveyard),
            counts(self.banished),
            self.normal_summon.value,
            tuple(sorted(self.effects_used)),
            tuple(sorted(self.restrictions)),
        )


@dataclass(slots=True)
class _NodeBuild:
    node_id: str
    name: str
    state: _CompileState
    result: RouteResult | None = None
    effects_not_used: set[str] = dataclass_field(default_factory=set)


def _resolve_counter(
    names: tuple[str, ...],
    resolver: CardNameResolver,
    *,
    context: str,
) -> Counter[int]:
    return Counter(
        resolver.resolve(name, context=f"{context}[{index}]")
        for index, name in enumerate(names)
    )


def _remove_cards(
    zone: Counter[int],
    removals: Counter[int],
    *,
    zone_name: str,
    context: str,
) -> None:
    missing = {
        card_id: count - zone[card_id]
        for card_id, count in removals.items()
        if zone[card_id] < count
    }
    if missing:
        raise ValueError(
            f"{context} removes cards that are not present in {zone_name}: {missing}"
        )
    zone.subtract(removals)
    for card_id in tuple(zone):
        if zone[card_id] == 0:
            del zone[card_id]


def _validate_known_card_counts(
    state: _CompileState,
    deck_counts: Counter[int],
    *,
    context: str,
) -> None:
    known = state.hand + state.field + state.graveyard + state.banished
    excessive = {
        card_id: (count, deck_counts[card_id])
        for card_id, count in known.items()
        if count > deck_counts[card_id]
    }
    if excessive:
        raise ValueError(
            f"{context} tracks more known copies than the supplied YDK contains: {excessive}"
        )


def _apply_changes(
    state: _CompileState,
    changes: DraftStateChanges,
    resolver: CardNameResolver,
    deck_counts: Counter[int],
    *,
    context: str,
) -> _CompileState:
    result = state.copy()
    zones = (
        ("hand", result.hand, changes.hand_add, changes.hand_remove),
        ("field", result.field, changes.field_add, changes.field_remove),
        ("graveyard", result.graveyard, changes.graveyard_add, changes.graveyard_remove),
        ("banished", result.banished, changes.banished_add, changes.banished_remove),
    )
    for zone_name, zone, additions, removals in zones:
        removal_counts = _resolve_counter(
            removals, resolver, context=f"{context}.changes.{zone_name}_remove"
        )
        addition_counts = _resolve_counter(
            additions, resolver, context=f"{context}.changes.{zone_name}_add"
        )
        _remove_cards(zone, removal_counts, zone_name=zone_name, context=context)
        zone.update(addition_counts)
    if changes.normal_summon is not None:
        result.normal_summon = changes.normal_summon
    result.effects_used.update(changes.effects_used)
    result.restrictions.difference_update(changes.restrictions_remove)
    result.restrictions.update(changes.restrictions_add)
    _validate_known_card_counts(result, deck_counts, context=context)
    return result


def _initial_state(
    route: DraftRoute,
    resolver: CardNameResolver,
    deck_counts: Counter[int],
) -> _CompileState:
    state = _CompileState(
        hand=_resolve_counter(route.starting_hand, resolver, context=f"route {route.route_id}.starting_hand"),
        field=_resolve_counter(route.starting_field, resolver, context=f"route {route.route_id}.starting_field"),
        graveyard=_resolve_counter(route.starting_graveyard, resolver, context=f"route {route.route_id}.starting_graveyard"),
        banished=_resolve_counter(route.starting_banished, resolver, context=f"route {route.route_id}.starting_banished"),
        normal_summon=route.normal_summon,
    )
    _validate_known_card_counts(state, deck_counts, context=f"route {route.route_id} start")
    return state


def _requirement(node: _NodeBuild) -> StateRequirement:
    return StateRequirement(
        hand_contains=dict(sorted(node.state.hand.items())),
        field_contains=dict(sorted(node.state.field.items())),
        graveyard_contains=dict(sorted(node.state.graveyard.items())),
        banished_contains=dict(sorted(node.state.banished.items())),
        normal_summon=node.state.normal_summon,
        effects_not_used=tuple(sorted(node.effects_not_used)),
        effects_used=tuple(sorted(node.state.effects_used)),
        required_restrictions=tuple(sorted(node.state.restrictions)),
    )


def compile_combo_draft(
    draft: ComboDraft,
    deck: DeckList,
    resolver: CardNameResolver,
) -> ComboGraph:
    deck_counts = deck.counts()
    nodes_by_signature: dict[tuple, _NodeBuild] = {}
    node_order: list[_NodeBuild] = []
    edges: list[ComboEdge] = []
    edge_keys: set[tuple] = set()

    def get_node(
        state: _CompileState,
        *,
        name: str,
        result: RouteResult | None = None,
    ) -> _NodeBuild:
        signature = state.signature()
        node = nodes_by_signature.get(signature)
        if node is None:
            node = _NodeBuild(
                node_id=f"n{len(node_order) + 1:04d}",
                name=name,
                state=state.copy(),
                result=result,
            )
            nodes_by_signature[signature] = node
            node_order.append(node)
        elif result is not None:
            if node.result is not None and node.result != result:
                raise ValueError(
                    f"State shared by multiple routes has conflicting terminal results: {node.name!r}"
                )
            node.result = result
            node.name = name
        return node

    for route in draft.routes:
        current_state = _initial_state(route, resolver, deck_counts)
        current_node = get_node(current_state, name=f"{route.name} - 起点")

        for step_index, step in enumerate(route.steps):
            context = f"route {route.route_id} step {step_index + 1}"
            card_id = (
                resolver.resolve(step.card, context=f"{context}.card")
                if step.card is not None
                else None
            )
            target_card_id = (
                resolver.resolve(step.target_card, context=f"{context}.target_card")
                if step.target_card is not None
                else None
            )
            if step.effect_id is not None:
                if step.effect_id in current_state.effects_used:
                    raise ValueError(f"{context} reuses effect_id {step.effect_id!r}")
                current_node.effects_not_used.add(step.effect_id)

            next_state = _apply_changes(
                current_state,
                step.changes,
                resolver,
                deck_counts,
                context=context,
            )
            if step.effect_id is not None:
                next_state.effects_used.add(step.effect_id)
            if next_state.signature() == current_state.signature():
                raise ValueError(
                    f"{context} does not change the tracked state; add explicit changes "
                    "or an effect_id so the compiler can create a distinct step"
                )

            is_terminal = step_index == len(route.steps) - 1
            terminal_result = None
            if is_terminal:
                expected_board = _resolve_counter(
                    route.end_board,
                    resolver,
                    context=f"route {route.route_id}.end_board",
                )
                missing_end_board = expected_board - next_state.field
                if missing_end_board:
                    raise ValueError(
                        f"route {route.route_id} end_board is not present after its final step: "
                        f"{dict(missing_end_board)}"
                    )
                terminal_result = RouteResult(
                    end_board_score=route.result.end_board_score,
                    remaining_resource_score=route.result.remaining_resource_score,
                    follow_up_score=route.result.follow_up_score,
                    resilience_score=route.result.resilience_score,
                    remaining_hand=sum(next_state.hand.values()),
                    summary=route.result.summary,
                )
            next_node = get_node(
                next_state,
                name=(
                    f"{route.name} - 终场"
                    if is_terminal
                    else f"{route.name} - 步骤 {step_index + 1}"
                ),
                result=terminal_result,
            )
            action = ActionInstruction(
                action_type=step.action.value,
                card_id=card_id,
                instruction=step.instruction,
                effect_id=step.effect_id,
                target_card_id=target_card_id,
            )
            edge_key = (
                current_node.node_id,
                next_node.node_id,
                action.action_type,
                action.card_id,
                action.instruction,
                action.effect_id,
                action.target_card_id,
            )
            if edge_key not in edge_keys:
                edge_keys.add(edge_key)
                edges.append(
                    ComboEdge(
                        edge_id=f"e{len(edges) + 1:04d}",
                        from_node_id=current_node.node_id,
                        to_node_id=next_node.node_id,
                        action=action,
                    )
                )
            current_state = next_state
            current_node = next_node

    graph = ComboGraph(
        deck_pack_id=draft.deck_pack_id,
        version=draft.version,
        ruleset=draft.ruleset,
        verification_status=draft.verification_status,
        sources=draft.sources,
        nodes={
            node.node_id: ComboNode(
                node_id=node.node_id,
                name=node.name,
                requirement=_requirement(node),
                result=node.result,
            )
            for node in node_order
        },
        edges=tuple(edges),
    )
    graph.validate()
    return graph
