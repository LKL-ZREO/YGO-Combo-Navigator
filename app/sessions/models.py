from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from app.combos.models import RouteCandidate
from app.state.models import DuelState


class RouteProgressStatus(StrEnum):
    NOT_SELECTED = "NOT_SELECTED"
    SELECTED = "SELECTED"
    ADVANCED = "ADVANCED"
    COMPLETED = "COMPLETED"
    INTERRUPTED_OR_DEVIATED = "INTERRUPTED_OR_DEVIATED"


@dataclass(frozen=True, slots=True)
class SessionEvent:
    event_type: str
    message: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(slots=True)
class AnalysisSession:
    deck_pack_id: str
    session_id: str = field(default_factory=lambda: uuid4().hex)
    current_state: DuelState | None = None
    previous_state: DuelState | None = None
    selected_route: RouteCandidate | None = None
    current_path_index: int = 0
    events: list[SessionEvent] = field(default_factory=list)

