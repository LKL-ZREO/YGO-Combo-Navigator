from collections import Counter
from pathlib import Path

from app.combos.loader import load_combo_graph
from app.combos.matcher import RouteMatcher
from app.state.models import DuelState, Phase, UsageState
from app.tools.validate_deck_pack import validate


def test_kewl_tune_pack_validates() -> None:
    result = validate(Path("deck-packs/kewl-tune-md"))
    assert "10 nodes" in result
    assert "9 edges" in result
    assert "COMMUNITY_TRANSCRIBED" in result


def test_cue_start_returns_standard_route() -> None:
    graph = load_combo_graph(Path("deck-packs/kewl-tune-md/graph.json"))
    state = DuelState(
        hand=Counter({16387555: 1}),
        phase=Phase.MAIN1,
        normal_summon=UsageState.AVAILABLE,
        used_effects={"16387555:effect_1": UsageState.AVAILABLE},
    )

    routes = RouteMatcher().match(state, graph)

    assert routes
    assert routes[0].start_node_id == "cue_start"
    assert routes[0].terminal_node_id == "cue_standard_end"
    assert len(routes[0].actions) == 9
    assert routes[0].next_action.instruction == "通常召唤 Kewl Tune Cue。"

