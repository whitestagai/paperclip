# ctx-stats — Wöchentliche Kontext-Bedarf-Statistik der LM-Studio-Modelle

Ermittelt aus den LM-Studio-Server-Logs, wie viel Kontext die Modelle real nutzen,
und vergleicht das mit dem konfigurierten Kontextfenster. Entscheidungsvorlage fürs
ctx-Sizing (RAM vs. Overflow). Rein deterministisch, kein LLM.

## Dateien
- `ctx_report.py` — parst Logs (`total_tokens` = Prompt+Antwort je Call), bildet
  Perzentile (Vorwoche) + MAX (30 Tage), liest konfiguriertes ctx aus den
  Model-Configs, vergibt Ampel, schreibt HTML+JSON.
- `send_ctx_mail.sh` — sendet den HTML-Report über den n8n-Mailhub (cto@ → ws@).
- `run.sh` — Orchestrierung: Report bauen → mailen. `--dry-run` zum Testen.
- `routine-brief.md` — Anweisung für den ausführenden Agenten.
- `state/` — archivierte HTML/JSON-Reports je Lauf.

## Ampel
- **ROT**: konfiguriertes Fenster < p99-Bedarf → Kontext wird bei Spitzen abgeschnitten.
- **GELB**: < 1.2× p99 (zu knapp) ODER > 3× p99 (überdimensioniert, RAM sparbar).
- **GRÜN**: gesunder Puffer (1.2×–3× p99).
- **GRAU**: kein Fenster konfiguriert (JIT-geladenes/entladenes Modell).

## Manuell ausführen
```
bash ~/.paperclip/scripts/ctx-stats/run.sh --dry-run   # nur bauen, Mail simulieren
bash ~/.paperclip/scripts/ctx-stats/run.sh             # bauen + wirklich mailen
```

## Automatisierung
Paperclip-Routine `91fd6764-f06b-46c8-8bd6-043064f60579`
(„Wöchentliche Kontext-Bedarf-Statistik LM-Studio"), Agent **Online-Rechercheur**
(WHITESTAG), Cron `0 6 * * 1` Europe/Berlin (Montag 06:00).

## Datenquelle-Hinweis
Nicht aus `cost_events` (Paperclip-DB) rechnen: dort ist 1 Zeile = 1 ganzer Run,
über alle Iterationen aufsummiert (p99 ~686k) — das ist Durchsatz/Kosten, NICHT
Kontextbedarf. Nur die LM-Studio-Logs haben `prompt_tokens` je einzelnem Call.
