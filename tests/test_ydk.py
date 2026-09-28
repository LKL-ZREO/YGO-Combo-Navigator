import pytest

from app.decks.ydk import parse_ydk


def test_parse_ydk_sections_and_duplicates() -> None:
    deck = parse_ydk(
        """
#created by test
#main
14558127
14558127
23434538
#extra
84013237
!side
97268402
""",
        name="fixture",
    )

    assert deck.name == "fixture"
    assert deck.main == (14558127, 14558127, 23434538)
    assert deck.extra == (84013237,)
    assert deck.side == (97268402,)
    assert deck.all_card_ids() == (14558127, 23434538, 84013237, 97268402)
    assert deck.counts()[14558127] == 2


def test_parse_ydk_rejects_card_before_section() -> None:
    with pytest.raises(ValueError, match="before a section marker"):
        parse_ydk("14558127\n#main\n23434538")

