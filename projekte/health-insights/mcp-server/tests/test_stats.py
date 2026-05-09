import pytest
from paperclip_health_mcp.stats import summary_stats, linear_trend


def test_summary_stats_basic():
    s = summary_stats([1.0, 2.0, 3.0, 4.0, 5.0])
    assert s["min"] == 1.0
    assert s["max"] == 5.0
    assert s["mean"] == 3.0
    assert s["median"] == 3.0
    assert s["count"] == 5
    assert s["stddev"] == pytest.approx(1.5811, abs=1e-3)


def test_summary_stats_empty():
    assert summary_stats([]) == {
        "min": None, "max": None, "mean": None,
        "median": None, "stddev": None, "count": 0,
    }


def test_summary_stats_single_value():
    s = summary_stats([42.0])
    assert s["min"] == s["max"] == s["mean"] == s["median"] == 42.0
    assert s["stddev"] == 0.0
    assert s["count"] == 1


def test_linear_trend_rising():
    # values rise by 1 per index
    t = linear_trend([1.0, 2.0, 3.0, 4.0, 5.0])
    assert t["slope_per_step"] == pytest.approx(1.0, abs=1e-6)
    assert t["direction"] == "rising"


def test_linear_trend_flat():
    t = linear_trend([3.0, 3.0, 3.0, 3.0])
    assert t["slope_per_step"] == pytest.approx(0.0, abs=1e-6)
    assert t["direction"] == "flat"


def test_linear_trend_falling():
    t = linear_trend([10.0, 8.0, 6.0, 4.0])
    assert t["slope_per_step"] == pytest.approx(-2.0, abs=1e-6)
    assert t["direction"] == "falling"


def test_linear_trend_too_few_points():
    assert linear_trend([5.0])["direction"] == "insufficient_data"
    assert linear_trend([])["direction"] == "insufficient_data"
