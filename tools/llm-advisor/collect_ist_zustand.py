#!/usr/bin/env python3
"""Sammelt den Ist-Zustand der LLM-Zuweisung in ein JSON für den Advisor-Agenten."""
from __future__ import annotations

import json
import sys
import datetime as _dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from advisor.telemetry import fetch_rows, aggregate_runs
from advisor.agents import fetch_agent_rows, agent_profiles
from advisor.resources import (fetch_ls, fetch_ps, fetch_device_names, parse_models,
                               budget_report, VRAM_LIMIT_GB)
from advisor.signals import annotate_profiles
from advisor.evidence import evidence_line
from advisor import market
from advisor.market import lade_key

OUT = Path(__file__).parent / "state" / "ist-zustand.json"
ABLEHNUNGEN = Path(__file__).parent / "state" / "abgelehnte-modelle.json"
ABLEHNUNGEN_VORLAGE = Path(__file__).parent / "state-vorlagen" / "abgelehnte-modelle.json"
AA_CACHE = Path(__file__).parent / "state" / "aa-cache.json"

SUCHFRAGE = ("neue MLX-Modelle fuer LM Studio 2026 Qwen Gemma Mistral "
             "Release lokale Modelle")

# Zeichen je Quelle. Bei 6000 (dem Vorgabewert des Diensts) trug `suche`
# 19.470 der 98.824 Zeichen des Dokuments -- ein Fuenftel, nur um zu sagen,
# was es Neues gibt. Das Erfolgskriterium des Umbaus ist eine SINKENDE
# Iterationszahl; ein aufgeblaehtes Dokument arbeitet dagegen. 1200 Zeichen
# reichen fuer Titel, Ankuendigung und Modellnamen. Ganz ohne Text ginge
# nicht: der Agent hat kein Web-Werkzeug und kann einer URL nicht folgen.
SUCH_ZEICHEN = 1200


def _stelle_ablehnungsliste_bereit():
    """Kopiert die Ablehnungs-Vorlage nach state/, wenn dort noch keine liegt.

    state/ ist git-ignored (siehe .gitignore); versioniert ist nur die
    Vorlage in state-vorlagen/. Ohne diese Kopie liefert lade_ablehnungen()
    bei einer fehlenden Datei dauerhaft {} zurueck -- die Ablehnung von
    qwen3.8-27b vom 17.08. wuerde nie wirksam und das Modell kaeme jede Woche
    neu zur Empfehlung. Eine bereits vorhandene Datei wird NIE ueberschrieben:
    sie traegt Walters spaetere Ablehnungen.

    Nur OSError (Vorlage fehlt, Ziel nicht schreibbar) wird hier lokal
    geschluckt. Eine kaputt kodierte Vorlage wirft UnicodeDecodeError -- eine
    ValueError-Unterklasse, kein OSError -- und muss deshalb ungefangen nach
    aussen durchschlagen: sammle_markt() ruft diese Funktion INNERHALB seines
    eigenen except Exception auf, das ist die einzige Stelle, die einen so
    breiten Fang rechtfertigt. Ein eigener breiter Fang hier wuerde diese
    Grenze verdoppeln und beim naechsten Aufrufer fehlen.
    """
    if ABLEHNUNGEN.exists():
        return
    try:
        ABLEHNUNGEN.parent.mkdir(parents=True, exist_ok=True)
        ABLEHNUNGEN.write_text(ABLEHNUNGEN_VORLAGE.read_text())
    except OSError:
        pass


def sammle_markt(lm_keys):
    """Marktdaten fuer den Bericht. Faellt nie hart aus.

    Der Agent bekommt fertige Fakten und braucht dafuer keine Iteration --
    aber dieser Aufruf steht in seinem Wallclock, denn dieses Skript ist
    Schritt 1 seines Briefs und laeuft nicht unter launchd. Deshalb hat
    jeder externe Abruf hier ein eigenes Zeitbudget.

    Der Ausfall-Rueckgabewert traegt dieselben Schluessel wie der Erfolgsfall,
    `aa_stand` und `quelle` eingeschlossen: der Brief macht die Angabe
    "Quelle: Artificial Analysis, Stand <aa_stand>" zur Pflicht, und ein
    fehlender Schluessel laesst den Agenten dort raten.
    """
    try:
        _stelle_ablehnungsliste_bereit()
        aa = market.fetch_aa(lade_key(), cache_pfad=AA_CACHE)
        web = market.fetch_web(SUCHFRAGE, zeichen=SUCH_ZEICHEN)
        return market.market_report(
            lm_keys, aa, web, ablehnungen=market.lade_ablehnungen(ABLEHNUNGEN))
    except Exception as e:  # noqa: BLE001 -- Nebenquelle darf den Lauf nie kippen
        return market.nicht_verfuegbar(
            "%s: %s" % (type(e).__name__, e),
            aa_stand=None, quelle=None, aa_hinweis=None,
            modelle={}, nicht_gelistet=[], suche=None)


def main(days: int = 7, generated_at: str | None = None):
    telemetry = aggregate_runs(fetch_rows(days))
    profiles = agent_profiles(fetch_agent_rows())
    device_names = fetch_device_names()
    all_models = parse_models(fetch_ls(), device_names=device_names)
    loaded = parse_models(fetch_ps(), device_names=device_names)
    budget = budget_report(all_models, loaded, limit_gb=VRAM_LIMIT_GB)
    # Bewertet wird, was die Agenten FAHREN -- nicht nur, was auf dieser Platte
    # liegt. `models_on_disk` stammt aus `lms ls` dieses Geraets; Modelle auf
    # dem remote gelinkten MacBook fehlen darin. Der erste echte Lauf (21.08.)
    # liess deshalb 26 von 40 Agenten ohne Marktzahlen zurueck, darunter die 22
    # auf `gemma-4-31b-it-mlx`. Die Platte bleibt trotzdem drin: ein geladenes,
    # noch keinem Agenten zugewiesenes Modell ist ein moeglicher Kandidat.
    modell_keys = {m["model_key"] for m in all_models if m.get("model_key")}
    modell_keys |= {p["model"] for p in profiles if p.get("model")}
    markt = sammle_markt(sorted(modell_keys))

    tel_by_agent = {t["agent_id"]: t for t in telemetry}
    for p in profiles:
        p["telemetry"] = tel_by_agent.get(p["agent_id"], {})
        # Fertig gerenderte Fehlerlage: der Agent uebernimmt diese Zeile,
        # statt Zahlen zu formulieren. Am 31.07. stand im Approval
        # "5x llm_error + 5x adapter_failed" bei llm_error=0 (WHI-3389).
        p["evidence"] = evidence_line(p["telemetry"], window_days=days)
    # Ursachen-Urteil und Geraete-/Kontext-Fakten je Agent (WHI-3362).
    annotate_profiles(profiles, tel_by_agent, {m["model_key"]: m for m in loaded})

    doc = {
        "generated_at": generated_at or _dt.datetime.now().isoformat(timespec="seconds"),
        "window_days": days,
        "budget": budget,
        "models_on_disk": all_models,
        "model_market": markt,
        "agents": profiles,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str))
    print(f"wrote {OUT} — {len(profiles)} agents, {len(all_models)} models, "
          f"loaded {budget['loaded_gb']}/{budget['limit_gb']} GB")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"collect_ist_zustand FEHLER: {type(e).__name__}: {e}\n")
        sys.exit(1)
