#!/usr/bin/env python3
"""Tests für die reine Entscheidungslogik des Frische-Wächters."""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_ingest_monitor as m  # noqa: E402

TODAY = date(2026, 7, 19)
YESTERDAY = "2026-07-18"


def src(newest=None, dataless=None, recent=None, dir_exists=True):
    return {
        "dir_exists": dir_exists,
        "newest_date": newest,
        "recent_files": recent if recent is not None else ([(newest, "/x")] if newest else []),
        "dataless_recent": dataless or [],
        "total_files": len(recent) if recent else (1 if newest else 0),
    }


def db(daily_max=None, max_ing="2026-07-19 00:00:00+02", runs=None):
    return {
        "daily_max_date": daily_max,
        "max_ingested_at": max_ing,
        "latest_runs": runs or [],
    }


def test_green_when_yesterday_present():
    v = m.classify(src(newest=YESTERDAY), db(daily_max="2026-07-18"), TODAY)
    assert v["state"] == "green", v


def test_green_when_daily_ahead_of_yesterday():
    v = m.classify(src(newest="2026-07-19"), db(daily_max="2026-07-19"), TODAY)
    assert v["state"] == "green", v


def test_red_source_when_no_recent_file():
    # DB hängt UND keine Quelldatei für gestern -> SOURCE (iPhone liefert nicht)
    v = m.classify(src(newest="2026-07-15"), db(daily_max="2026-07-15"), TODAY)
    assert v["state"] == "red" and v["layer"] == "SOURCE", v


def test_red_source_when_dir_missing():
    v = m.classify(src(dir_exists=False), db(daily_max="2026-07-10"), TODAY)
    assert v["state"] == "red" and v["layer"] == "SOURCE", v


def test_red_materialization_when_dataless():
    # Quelldatei für gestern da, aber dataless -> MATERIALIZATION
    v = m.classify(
        src(newest=YESTERDAY, dataless=["/x/Gesundheitsdaten-2026-07-18.json"]),
        db(daily_max="2026-07-16"), TODAY,
    )
    assert v["state"] == "red" and v["layer"] == "MATERIALIZATION", v


def test_red_ingest_when_file_ok_but_db_stale():
    # Quelldatei da + materialisiert, DB hängt -> INGEST
    v = m.classify(src(newest=YESTERDAY, dataless=[]), db(daily_max="2026-07-16"), TODAY)
    assert v["state"] == "red" and v["layer"] == "INGEST", v


def test_build_issue_contains_layer_and_evidence():
    v = m.classify(src(newest=YESTERDAY, dataless=[]), db(daily_max="2026-07-16",
                   runs=[{"date": "2026-07-18", "status": "ready", "samples": 0}]), TODAY)
    title, body = m.build_issue(v, src(newest=YESTERDAY), db(daily_max="2026-07-16"))
    assert "INGEST" in title
    assert "2026-07-18" in title
    assert "Ground-Truth-Evidenz" in body


def test_ingested_age_hours_parses_pg_timestamp():
    from datetime import datetime
    age = m.ingested_age_hours("2026-07-19 00:00:00+02",
                               now=datetime(2026, 7, 19, 6, 0, 0))
    assert age is not None and 5.9 < age < 6.1, age


def test_ingested_age_none_on_empty():
    assert m.ingested_age_hours(None) is None
    assert m.ingested_age_hours("") is None


def _run():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} Tests grün")


if __name__ == "__main__":
    _run()
