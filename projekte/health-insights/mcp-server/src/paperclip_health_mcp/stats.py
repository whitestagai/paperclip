"""Numerical helpers for time-series summaries.

These run in Python (not Postgres) because the row counts are small —
we only operate on already-aggregated daily values.
"""
import statistics
from typing import Sequence


def summary_stats(values: Sequence[float]) -> dict:
    """min/max/mean/median/stddev for a list of floats. Empty list -> all None."""
    if not values:
        return {"min": None, "max": None, "mean": None,
                "median": None, "stddev": None, "count": 0}
    if len(values) == 1:
        v = float(values[0])
        return {"min": v, "max": v, "mean": v, "median": v,
                "stddev": 0.0, "count": 1}
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stddev": statistics.stdev(values),
        "count": len(values),
    }


def linear_trend(values: Sequence[float], flat_threshold: float = 0.05) -> dict:
    """Least-squares slope per step plus direction label.

    Direction labels: rising | falling | flat | insufficient_data.
    flat_threshold is in absolute slope_per_step terms; below it we report flat.
    """
    n = len(values)
    if n < 2:
        return {"slope_per_step": None, "direction": "insufficient_data"}
    # least-squares slope: sum((x - x_mean)(y - y_mean)) / sum((x - x_mean)^2)
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    if abs(slope) < flat_threshold:
        direction = "flat"
    elif slope > 0:
        direction = "rising"
    else:
        direction = "falling"
    return {"slope_per_step": slope, "direction": direction}
