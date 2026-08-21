# Link-Detektor-Aufsicht

Wöchentlicher Gesundheitscheck der Verlinkungs-Kette im WHITESTAG-Vault.
Der Wächter **repariert nichts** — er stellt fest und meldet.

## Warum

Der v11-Daemon verarbeitete vom 21.06. bis zum 30.07.2026 **sechs Wochen lang
keinen einzigen Job**: 45.000 Fehl-Jobs durch `spawn EBADF`. Niemand merkte es,
weil beide LaunchAgents „running" zeigten und die Logs niemand liest. Genau
diese Lücke schließt dieser Wächter.

## Aufbau

| Datei | Zweck |
|---|---|
| `pruefung.py` | reine Bewertungslogik, kein I/O — hier stehen die Schwellen samt Begründung |
| `waechter.py` | holt die Kennzahlen, gibt JSON auf stdout |
| `test_pruefung.py` | die Ernstfälle, die im Betrieb hoffentlich nie eintreten |
| `test_waechter.py` | Fail-closed: eine unlesbare Quelle ist ein Befund, nie Entwarnung |

Die Trennung ist Absicht (Muster von `backup-waechter`): Genau die Entscheidung,
die im Ernstfall zählt, muss prüfbar sein, ohne den Ernstfall herbeizuführen.

## Aufruf

```
/usr/bin/python3 ~/.paperclip/scripts/link-detektor-wacht/waechter.py
```

Ausgabe: `{"ok": bool, "probleme": [...], "zeilen": [...]}`. Die `zeilen` sind
fertige Sätze zum wörtlichen Zitieren — dieselbe Konstruktion wie
`evidence_line` beim LLM-Advisor, damit der Agent Zahlen kopiert statt tippt.

## Geprüft wird

- **v11-Daemon** über `ld.job_queue` (Postgres `link_detektor`): Stillstand
  (>7 Tage ohne erledigten Job), Fehlerquote (>20 % bei mindestens 20 Joben),
  hängende Jobs (>2 h auf `running`; ein Job dauert normal 70–90 s)
- **n8n `Link-Detektor V10.2`** über `~/.n8n/database.sqlite`: kein
  erfolgreicher Lauf seit >48 h (der Workflow feuert täglich 01:00)

Jede Schwelle ist in `pruefung.py` begründet. Wer sie ändert, ändert sie dort —
nicht im Agenten-Brief.

## Fail-closed

Eine nicht erreichbare Datenquelle ist selbst ein Befund, nie ein stilles
„alles in Ordnung". Ein Wächter, der bei kaputter Datenbank Ruhe meldet, ist
schlimmer als keiner: er erzeugt Vertrauen, das er nicht deckt.

## Betrieb

Paperclip-Routine `9370181d-39b1-49a0-9fbb-dfd919c69af8`
(„Link-Detektor-Aufsicht", Mo 08:00), Agent **Link-Detektor** `caaeb345`.
Ohne Befund passiert nichts; bei Befund legt der Agent ein Issue ohne Assignee
im WHITESTAG-Projekt an.

Die Rolle des Agenten liegt in
`~/.paperclip/scripts/agents-instructions/roles/link-detektor.role.md` und wird
über `build-agents-md.py` verteilt — **nie direkt in die AGENTS.md schreiben**,
der Nacht-Loop überschreibt sie. Der Generator braucht `PCP_TOKEN` und
`PCP_CID` in der Umgebung.
