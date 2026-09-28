from collections import Counter

from app.state.models import DuelState, Phase, UsageState
from app.state.observation import BoardObservation
from app.state.reducer import reduce_observation


def test_visible_cards_replace_snapshot_while_history_is_retained() -> None:
    previous = DuelState(
        hand=Counter({1: 1, 2: 1}),
        field=Counter({3: 1}),
        known_graveyard=Counter({9: 1}),
        phase=Phase.MAIN1,
        normal_summon=UsageState.USED,
        used_effects={"1:e1": UsageState.USED},
    )
    observation = BoardObservation(
        hand=Counter({2: 1}),
        field=Counter({1: 1, 3: 1}),
        confidence=0.9,
    )

    current = reduce_observation(previous, observation)

    assert current.hand == Counter({2: 1})
    assert current.field == Counter({1: 1, 3: 1})
    assert current.known_graveyard == Counter({9: 1})
    assert current.normal_summon == UsageState.USED
    assert current.used_effects["1:e1"] == UsageState.USED
    assert current.recognition_confidence == 0.9

