from __future__ import annotations

from dataclasses import dataclass, field

from app.state.models import Phase, UsageState


@dataclass(frozen=True, slots=True)
class StateRequirement:
    hand_contains: dict[int, int] = field(default_factory=dict)
    field_contains: dict[int, int] = field(default_factory=dict)
    graveyard_contains: dict[int, int] = field(default_factory=dict)
    banished_contains: dict[int, int] = field(default_factory=dict)
    normal_summon: UsageState | None = None
    effects_not_used: tuple[str, ...] = ()
    effects_used: tuple[str, ...] = ()
    forbidden_restrictions: tuple[str, ...] = ()
    required_restrictions: tuple[str, ...] = ()
    allowed_phases: tuple[Phase, ...] = (Phase.MAIN1, Phase.MAIN2, Phase.UNKNOWN)


@dataclass(frozen=True, slots=True)
class ActionInstruction:
    action_type: str
    card_id: int | None
    instruction: str
    effect_id: str | None = None
    target_card_id: int | None = None


@dataclass(frozen=True, slots=True)
class RouteResult:
    end_board_score: float
    remaining_resource_score: float
    follow_up_score: float
    resilience_score: float
    remaining_hand: int | None = None
    summary: str = ""


@dataclass(frozen=True, slots=True)
class ComboNode:
    node_id: str
    name: str
    requirement: StateRequirement
    result: RouteResult | None = None


@dataclass(frozen=True, slots=True)
class ComboEdge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    action: ActionInstruction
    outcome: str = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class ComboGraph:
    deck_pack_id: str
    version: str
    ruleset: str
    verification_status: str
    sources: tuple[str, ...]
    nodes: dict[str, ComboNode]
    edges: tuple[ComboEdge, ...]

    def outgoing(self, node_id: str) -> tuple[ComboEdge, ...]:
        return tuple(edge for edge in self.edges if edge.from_node_id == node_id)

    def validate(self) -> None:
        if not self.nodes:
            raise ValueError("Combo graph must contain at least one node")
        if self.verification_status not in {"VERIFIED", "COMMUNITY_TRANSCRIBED", "DRAFT"}:
            raise ValueError(f"Unsupported verification status: {self.verification_status}")
        for edge in self.edges:
            if edge.from_node_id not in self.nodes:
                raise ValueError(f"Unknown source node: {edge.from_node_id}")
            if edge.to_node_id not in self.nodes:
                raise ValueError(f"Unknown destination node: {edge.to_node_id}")


@dataclass(frozen=True, slots=True)
class RequirementMatch:
    matched: bool
    confidence: float
    unresolved: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    start_node_id: str
    terminal_node_id: str
    node_path: tuple[str, ...]
    actions: tuple[ActionInstruction, ...]
    result: RouteResult
    score: float
    confidence: float
    unresolved_requirements: tuple[str, ...]

    @property
    def next_action(self) -> ActionInstruction | None:
        return self.actions[0] if self.actions else None

