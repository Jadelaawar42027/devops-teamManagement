import pytest

from routing.service import band_for_score, score_from_results


def test_hot_lead_dropped_scores_negative():
    assert score_from_results([(0, "hot", 0)]) == -2.5


def test_cold_lead_closed_scores_positive():
    assert score_from_results([(4, "cold", 0)]) == 3.5


def test_recency_decay_halves_every_30_days():
    fresh = score_from_results([(4, "hot", 0)])
    month_old = score_from_results([(4, "hot", 30)])
    two_months_old = score_from_results([(4, "hot", 60)])
    assert fresh == 1.5
    assert month_old == pytest.approx(fresh / 2)
    assert two_months_old == pytest.approx(fresh / 4)


def test_results_are_summed():
    results = [(4, "cold", 0), (0, "hot", 0), (2, "warm", 30)]
    assert score_from_results(results) == pytest.approx(3.5 - 2.5 + 0.25)


def test_empty_history_returns_zero():
    assert score_from_results([]) == 0


def test_band_boundary_at_40():
    assert band_for_score(39) == "cold"
    assert band_for_score(40) == "warm"


def test_band_boundary_at_70():
    assert band_for_score(69) == "warm"
    assert band_for_score(70) == "hot"


def test_band_extremes():
    assert band_for_score(0) == "cold"
    assert band_for_score(100) == "hot"
