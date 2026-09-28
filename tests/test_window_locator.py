from app.capture.window_locator import title_matches


def test_title_matching_is_case_insensitive() -> None:
    assert title_matches("Yu-Gi-Oh! MASTER DUEL")
    assert title_matches("MASTER DUEL")
    assert title_matches("masterduel")
    assert title_matches("游戏王：大师决斗")


def test_title_matching_rejects_unrelated_window() -> None:
    assert not title_matches("Visual Studio Code")

