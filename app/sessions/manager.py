from __future__ import annotations

from dataclasses import dataclass

from app.combos.matcher import RouteMatcher, match_requirement
from app.combos.models import ComboGraph, RouteCandidate
from app.sessions.models import AnalysisSession, RouteProgressStatus, SessionEvent
from app.state.observation import BoardObservation
from app.state.reducer import reduce_observation


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    routes: tuple[RouteCandidate, ...]
    progress_status: RouteProgressStatus
    message: str


class SessionManager:
    def __init__(self, graph: ComboGraph, *, matcher: RouteMatcher | None = None) -> None:
        self.graph = graph
        self.matcher = matcher or RouteMatcher()
        self.session = AnalysisSession(deck_pack_id=graph.deck_pack_id)

    def start_new(self) -> AnalysisSession:
        self.session = AnalysisSession(deck_pack_id=self.graph.deck_pack_id)
        self.session.events.append(SessionEvent("SESSION_STARTED", "Started a new duel session"))
        return self.session

    def analyze(self, observation: BoardObservation, *, limit: int = 5) -> AnalysisResult:
        self.session.previous_state = (
            self.session.current_state.copy() if self.session.current_state is not None else None
        )
        self.session.current_state = reduce_observation(
            self.session.current_state,
            observation,
        )
        progress_status, message = self._update_route_progress()
        routes = tuple(
            self.matcher.match(self.session.current_state, self.graph, limit=limit)
        )
        self.session.events.append(SessionEvent("STATE_ANALYZED", message))
        return AnalysisResult(routes=routes, progress_status=progress_status, message=message)

    def select_route(self, route: RouteCandidate) -> None:
        self.session.selected_route = route
        self.session.current_path_index = 0
        self.session.events.append(
            SessionEvent("ROUTE_SELECTED", f"Selected route to {route.terminal_node_id}")
        )

    def _update_route_progress(self) -> tuple[RouteProgressStatus, str]:
        route = self.session.selected_route
        state = self.session.current_state
        if route is None or state is None:
            return RouteProgressStatus.NOT_SELECTED, "Current state analyzed"
        if self.session.current_path_index >= len(route.node_path) - 1:
            return RouteProgressStatus.COMPLETED, "Selected route is already complete"

        next_index = self.session.current_path_index + 1
        next_node_id = route.node_path[next_index]
        next_node = self.graph.nodes[next_node_id]
        next_match = match_requirement(next_node.requirement, state)
        if next_match.matched:
            self.session.current_path_index = next_index
            if next_index == len(route.node_path) - 1:
                return RouteProgressStatus.COMPLETED, "Reached the selected route result"
            return RouteProgressStatus.ADVANCED, f"Advanced to route node {next_node_id}"

        current_node_id = route.node_path[self.session.current_path_index]
        current_match = match_requirement(self.graph.nodes[current_node_id].requirement, state)
        if current_match.matched:
            return RouteProgressStatus.SELECTED, "Selected route has not advanced yet"
        return (
            RouteProgressStatus.INTERRUPTED_OR_DEVIATED,
            "The selected route no longer matches; replanned from the observed state",
        )

