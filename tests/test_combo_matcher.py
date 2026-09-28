from collections import Counter
from pathlib import Path

from app.combos.loader import load_combo_graph
from app.combos.matcher import RouteMatcher, match_requirement
from app.combos.models import StateRequirement
from app.state.models import DuelState, Phase, UsageState


def test_unknown_usage_reduces_confidence_without_rejecting() -> None:
    requirement = StateRequirement(
        hand_contains={1001: 1},
        normal_summon=UsageState.AVAILABLE,
        effects_not_used=("1001:effect_1",),
        allowed_phases=(Phase.MAIN1,),
    )
    state = DuelState(
        hand=Counter({1001: 1}),
        phase=Phase.MAIN1,
        normal_summon=UsageState.UNKNOWN,
        recognition_confidence=0.95,
    )

    result = match_requirement(requirement, state)

    assert result.matched is True
    assert set(result.unresolved) == {"normal_summon", "effect_unknown:1001:effect_1"}
    assert result.confidence < 0.95


def test_known_used_effect_rejects_node() -> None:
    requirement = StateRequirement(effects_not_used=("1001:effect_1",))
    state = DuelState(used_effects={"1001:effect_1": UsageState.USED})

    result = match_requirement(requirement, state)

    assert result.matched is False
    assert "effect_used:1001:effect_1" in result.failures


def test_route_matcher_can_enter_graph_from_start_or_middle() -> None:
    graph = load_combo_graph(Path("deck-packs/example/graph.json"))
    matcher = RouteMatcher()

    start_state = DuelState(
        hand=Counter({1001: 1}),
        phase=Phase.MAIN1,
        normal_summon=UsageState.AVAILABLE,
        used_effects={"1001:effect_1": UsageState.AVAILABLE},
    )
    start_routes = matcher.match(start_state, graph)
    assert start_routes[0].start_node_id == "start"
    assert start_routes[0].next_action is not None
    assert start_routes[0].next_action.action_type == "NORMAL_SUMMON"

    middle_state = DuelState(field=Counter({1001: 1}), phase=Phase.MAIN1)
    middle_routes = matcher.match(middle_state, graph)
    assert middle_routes[0].start_node_id == "end"
    assert middle_routes[0].actions == ()


def test_missing_card_filters_route() -> None:
    graph = load_combo_graph(Path("deck-packs/example/graph.json"))
    state = DuelState(hand=Counter(), field=Counter(), phase=Phase.MAIN1)

    routes = RouteMatcher().match(state, graph)

    assert routes == []

