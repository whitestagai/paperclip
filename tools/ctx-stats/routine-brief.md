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
4. vergibt eine Ampel (ROT = Fenster < p99-Bedarf → Overflow-Risiko; GELB = zu knapp
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
