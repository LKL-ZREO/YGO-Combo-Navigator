from collections import Counter
from pathlib import Path

from app.combos.loader import load_combo_graph
from app.combos.matcher import RouteMatcher
from app.decks.ydk import load_ydk
from app.state.models import DuelState, Phase, UsageState
from app.tools.validate_deck_pack import validate


PACK_ROOT = Path("deck-packs/crimson-powerforce-md")


def test_crimson_powerforce_ydk_matches_one_structure_deck() -> None:
    deck = load_ydk(PACK_ROOT / "crimson-powerforce-structure.ydk")

    assert len(deck.main) == 40
    assert len(deck.extra) == 8
    assert not deck.side
    assert Counter(deck.main) == Counter(
        {
            98396890: 1,
            62991792: 3,
            25784595: 3,
            77360173: 3,
            40975574: 3,
            34761841: 3,
            19299793: 3,
            5780210: 1,
            52589809: 3,
            98173209: 2,
            23008320: 3,
            8559524: 2,
            51779204: 2,
            5376159: 2,
            50056656: 2,
            50078509: 2,
            24662957: 2,
        }
    )
    assert Counter(deck.extra) == Counter(
        {
            87451661: 1,
            9753964: 1,
            97489701: 1,
            66141736: 2,
            87837090: 1,
            70902743: 1,
            36857073: 1,
        }
    )


def test_crimson_powerforce_pack_validates() -> None:
    result = validate(PACK_ROOT)

    assert "26 nodes" in result
    assert "25 edges" in result
    assert "2 results" in result
    assert "COMMUNITY_TRANSCRIBED" in result
    assert "deck 40 main/8 extra/0 side" in result


def test_soul_start_returns_two_end_board_choices() -> None:
    graph = load_combo_graph(PACK_ROOT / "graph.json")
    state = DuelState(
        hand=Counter({62991792: 1, 50078509: 1}),
        phase=Phase.MAIN1,
        normal_summon=UsageState.AVAILABLE,
        used_effects={"62991792:search": UsageState.AVAILABLE},
    )

    routes = RouteMatcher().match(state, graph)

    assert {route.terminal_node_id for route in routes} == {
        "abyss_bane_standard_end",
        "red_nova_standard_end",
    }
    assert routes[0].terminal_node_id == "abyss_bane_standard_end"
    assert routes[0].next_action is not None
    assert routes[0].next_action.card_id == 62991792


def test_search_spell_and_two_card_starts_join_the_shared_core() -> None:
    graph = load_combo_graph(PACK_ROOT / "graph.json")
    matcher = RouteMatcher()

    call_routes = matcher.match(
        DuelState(
            hand=Counter({23008320: 1, 50078509: 1}),
            phase=Phase.MAIN1,
            normal_summon=UsageState.AVAILABLE,
            used_effects={"23008320:activate": UsageState.AVAILABLE},
        ),
        graph,
    )
    wildwind_routes = matcher.match(
        DuelState(
            hand=Counter({34761841: 1, 52589809: 1}),
            phase=Phase.MAIN1,
            normal_summon=UsageState.USED,
            used_effects={
                "34761841:summon": UsageState.AVAILABLE,
                "34761841:deck_summon": UsageState.AVAILABLE,
            },
        ),
        graph,
    )

    assert call_routes[0].next_action is not None
    assert call_routes[0].next_action.card_id == 23008320
    assert wildwind_routes[0].next_action is not None
    assert wildwind_routes[0].next_action.card_id == 34761841
    assert {route.terminal_node_id for route in wildwind_routes} == {
        "abyss_bane_standard_end",
        "red_nova_standard_end",
    }


def test_gaia_start_does_not_try_to_search_with_gaia_twice() -> None:
    graph = load_combo_graph(PACK_ROOT / "graph.json")
    routes = RouteMatcher().match(
        DuelState(
            hand=Counter({98173209: 1}),
            phase=Phase.MAIN1,
            normal_summon=UsageState.AVAILABLE,
            used_effects={"98173209:search": UsageState.AVAILABLE},
        ),
        graph,
    )

    assert routes
    for route in routes:
        gaia_actions = [action for action in route.actions if action.card_id == 98173209]
        assert len(gaia_actions) == 1
        assert any(action.target_card_id == 50056656 for action in route.actions)


def test_combo_graph_only_references_cards_in_the_structure_deck() -> None:
    deck = load_ydk(PACK_ROOT / "crimson-powerforce-structure.ydk")
    graph = load_combo_graph(PACK_ROOT / "graph.json")
    deck_card_ids = set(deck.all_card_ids())
    referenced_card_ids: set[int] = set()

    for node in graph.nodes.values():
        referenced_card_ids.update(node.requirement.hand_contains)
        referenced_card_ids.update(node.requirement.field_contains)
        referenced_card_ids.update(node.requirement.graveyard_contains)
    for edge in graph.edges:
        if edge.action.card_id is not None:
            referenced_card_ids.add(edge.action.card_id)
        if edge.action.target_card_id is not None:
            referenced_card_ids.add(edge.action.target_card_id)

    assert referenced_card_ids <= deck_card_ids
