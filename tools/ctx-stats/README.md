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

## Warum die Overflows gezählt werden (seit 23.08.2026)

p99 und MAX stammen aus den `usage`-Blöcken **erfolgreicher** Aufrufe. Ein
Prompt, der am Kontextfenster scheitert, erzeugt nie eine solche Zeile und
fällt komplett aus der Statistik — die Messung bestätigt sich selbst.

Am 23.08.2026 meldete der Bericht deshalb **„0 ROT"**, während allein
`gemma4-31b-it` an dem Tag 129 Aufrufe genau daran verlor. Seitdem werden die
`Context size has been exceeded`-Blöcke direkt gezählt; eine gezählte Zahl
überstimmt jede Schätzung. Gleicher Lauf danach: **4 ROT, 474 Overflows.**

Zuordnungsfalle: das Modell steht nur in der Kopfzeile des Fehlerblocks
(`[ERROR][modell]`), die Ursache erst in einem `- Caused By:`-Nachsatz mehrere
Zeilen später. Wer nur nach dem Fehlertext greppt, kann ihn keinem Modell
zuordnen; wer nur die Kopfzeile liest, sieht die Ursache nicht.
