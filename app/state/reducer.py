from __future__ import annotations

from app.state.models import DuelState
from app.state.observation import BoardObservation


def reduce_observation(
    previous: DuelState | None,
    observation: BoardObservation,
) -> DuelState:
    """Merge visible facts while retaining history for facts not observed."""

    state = previous.copy() if previous is not None else DuelState()
    if observation.hand is not None:
        state.hand = observation.hand.copy()
    if observation.field is not None:
        state.field = observation.field.copy()
    if observation.known_graveyard is not None:
        state.known_graveyard = observation.known_graveyard.copy()
    if observation.known_banished is not None:
        state.known_banished = observation.known_banished.copy()
    if observation.phase is not None:
        state.phase = observation.phase
    if observation.normal_summon is not None:
        state.normal_summon = observation.normal_summon
    if observation.used_effects is not None:
        state.used_effects.update(observation.used_effects)
    if observation.active_restrictions is not None:
        state.active_restrictions = set(observation.active_restrictions)
    state.recognition_confidence = observation.confidence
    return state

