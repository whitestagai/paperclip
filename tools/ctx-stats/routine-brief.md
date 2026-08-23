# Wöchentliche Kontext-Bedarf-Statistik (Routine-Brief)

Du bist der Online-Rechercheur. Diese Routine ist **deterministisch** — kein Denken,
keine Web-Recherche, keine Modelländerung. Du führst nur das Skript aus, das die
Statistik selbst erzeugt und mailt.

## Der einzige Schritt

Bash:

```
bash ~/.paperclip/scripts/ctx-stats/run.sh
```

Das Skript:
1. parst die LM-Studio-Server-Logs (`~/.lmstudio/server-logs`) der Vorwoche (7 Tage)
   und ermittelt je Modell `total_tokens` = Prompt + Antwort pro einzelnem LLM-Call,
2. bildet Perzentile (p50/p90/p95/p99) plus MAX über 30 Tage,
3. liest das **konfigurierte** Kontextfenster je Modell aus den LM-Studio-Model-Configs,
4. **zählt die tatsächlichen `Context size has been exceeded`-Fehler je Modell**
   und vergibt eine Ampel (ROT = gezählte Overflows ODER Fenster < p99-Bedarf; GELB = zu knapp
   oder überdimensioniert; GRÜN = gesunder Puffer),
5. mailt den HTML-Report über den n8n-Mailhub von `cto@whitestag.ai` an `ws@whitestag.ai`.

## Abschluss

- Meldet das Skript `gesendet (200)` → Issue auf **done**, Kurzkommentar mit der
  Betreffzeile (steht in der letzten `fertig:`-Zeile).
- Skriptfehler oder kein `200` → Issue auf **blocked**, Fehlerausgabe in den Kommentar.

**Ändere nie selbst ein Kontextfenster.** Der Report ist Entscheidungsvorlage für
Walter. Auffällige ROT/GELB-Befunde fließen zusätzlich in deine nächtliche
LLM-Advisor-Analyse ein (Schritt „passt die zugewiesene Kontextlänge zur realen
Nutzung?").

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
