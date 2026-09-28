from collections import Counter
from pathlib import Path

from app.combos.loader import load_combo_graph
from app.sessions.manager import SessionManager
from app.sessions.models import RouteProgressStatus
from app.state.models import Phase, UsageState
from app.state.observation import BoardObservation


def _starting_observation() -> BoardObservation:
    return BoardObservation(
        hand=Counter({1001: 1}),
        field=Counter(),
        phase=Phase.MAIN1,
        normal_summon=UsageState.AVAILABLE,
        used_effects={"1001:effect_1": UsageState.AVAILABLE},
    )


def test_session_advances_selected_route_after_expected_result() -> None:
    graph = load_combo_graph(Path("deck-packs/example/graph.json"))
    manager = SessionManager(graph)
    manager.start_new()
    initial = manager.analyze(_starting_observation())
    manager.select_route(initial.routes[0])

    result = manager.analyze(
        BoardObservation(
            hand=Counter(),
            field=Counter({1001: 1}),
            phase=Phase.MAIN1,
            normal_summon=UsageState.USED,
        )
    )

    assert result.progress_status == RouteProgressStatus.COMPLETED
    assert "Reached" in result.message


def test_session_marks_interrupted_route_and_replans() -> None:
    graph = load_combo_graph(Path("deck-packs/example/graph.json"))
    manager = SessionManager(graph)
    manager.start_new()
    initial = manager.analyze(_starting_observation())
    manager.select_route(initial.routes[0])

    result = manager.analyze(
        BoardObservation(
            hand=Counter(),
            field=Counter(),
            phase=Phase.MAIN1,
            normal_summon=UsageState.AVAILABLE,
        )
    )

    assert result.progress_status == RouteProgressStatus.INTERRUPTED_OR_DEVIATED
    assert result.routes == ()
    assert "replanned" in result.message

