---
title: Modellvergleich für die Recherche-Agenten
datum: 2026-08-17
typ: Messung
status: Abgeschlossen
zusammenfassung: qwen3.6-35b, qwen3.8-27b Q8 (RTX) und Sonnet über zehn Recherchefragen aus dem WHITESTAG-Alltag. Ergebnis: qwen3.6 bleibt.
---

# Modellvergleich für die Recherche-Agenten

## Anlass

Online-Rechercheur (WHITESTAG) und Recherche (Clara Sound) wurden am 17.08. von
`claude_local` auf `lmstudio_local` migriert, nachdem der lokale Websuche-Dienst
stand. Offen war, ob ein lokales Modell die Rolle inhaltlich trägt — und ob ein
kleineres Modell auf schnellerer Hardware mehr Durchsatz bringt.

## Aufbau

Zehn Fragen aus laufenden Baustellen: Yoast-Meta-Descriptions, n8n-Versionierung,
LM-Studio-Kontextfenster, DSGVO-Auftragsverarbeitung, Fördermittel NRW,
ComfyUI-VRAM, launchd, ElevenLabs-Kontingente, Obsidian Bases/Dataview,
openWakeWord-Training.

**Einmal gesucht, Material eingefroren** — alle Modelle bekamen exakt dieselben
Quellen. Sonst misst man Suchzufall statt Syntheseleistung. Der Auftrag war
wörtlich die Pflicht aus der `AGENTS.md` des Online-Rechercheurs: mindestens zwei
unabhängige Quellen je Aussage, Beleg mit URL und Abrufdatum, Struktur
Befund → Quelle → Datum → Vertrauensgrad, nichts erfinden, Hinweis des Dienstes
weitergeben, bei DSGVO und Fördermitteln Beratungsvorbehalt.

Eine der zehn Suchen schlug fehl (Exit 2, kein Treffer trotz erfolgreicher
Suche). Der Fall blieb bewusst im Satz: er prüft, ob ein Modell dann eskaliert
oder aus dem Gedächtnis antwortet.

## Ergebnis

Neun Fälle mit Material, je ein sauberer Lauf ohne Parallellast:

| | qwen3.6-35b (Mac, MLX 8bit) | qwen3.8-27b Q8 (RTX) | Sonnet 4.6 |
|---|---|---|---|
| Laufzeit Ø | 49,3 s | 137,2 s | 22,3 s |
| Spanne | 27 – 72 s | 28 – 289 s | 14 – 27 s |
| Genutzte Quellen | 24/24 | 24/24 | 18/24 |
| Abrufdatum | 9/9 | 9/9 | 8/9 |
| Vertrauensgrad | 9/9 | 9/9 | 7/9 |
| Hinweis weitergegeben | 7/9 | 9/9 | 7/9 |
| Beratungsvorbehalt | 2/2 | 2/2 | 1/2 |
| Quellen erfunden | 0 | 0 | 0 |
| Ø Länge | 106 Wörter | 106 Wörter | 169 Wörter |

**Kein Modell hat in dreißig Antworten eine Quelle erfunden.** Beim
fehlgeschlagenen Suchfall haben alle drei korrekt eskaliert statt zu raten.

## Was daraus folgt

**qwen3.6 bleibt.** Es hält die Regeln der Rolle mindestens so gut ein wie
Sonnet und schöpft das Material besser aus (24 gegen 18 Quellen). Sonnet
schreibt ausführlicher und ordnet besser ein, lässt dafür in einem Drittel der
Fälle Quellen liegen.

**qwen3.8-27b bringt keinen Gewinn.** Gleiche Qualität, gleiche Antwortlänge,
aber knapp dreimal so lange — obwohl kleiner und auf dedizierter RTX. Ursache
ist der Denkaufwand: 5.500 bis 55.400 Zeichen gegen 8.400 bis 16.100 bei
qwen3.6. Beim Fördermittel-Fall 55.398 Zeichen Denken und 289 Sekunden für eine
Antwort, die qwen3.6 in 72 Sekunden gleichwertig liefert. Das ist eine
Eigenschaft des Modells, nicht des Formats — die MLX-Variante wurde deshalb
nicht mehr gemessen.

## Grenzen dieser Messung

Neun Fälle, ein Lauf je Modell. Unterschiede von ein bis zwei Fällen sind
Rauschen: qwen3.6 kam in einem früheren Lauf auf 9/9 beim Weitergeben des
Hinweises, im sauberen auf 7/9 — gleiche Konfiguration, gleiche Fragen.
Belastbar sind nur die großen Abstände: Laufzeit (Faktor 2 bis 6),
Quellenausschöpfung (24 gegen 18), Denkaufwand.

Zwei Messfehler mussten unterwegs korrigiert werden und sind hier vermerkt,
damit eine Wiederholung nicht hineinläuft:

- **`max_tokens` zu knapp.** Mit 2000 Token verbrauchte qwen3.6 das Budget im
  Denkfeld und lieferte in acht von zehn Fällen eine leere Antwort
  (`finish=length`). Es brauchte 2127. Denkende Modelle brauchen hier deutlich
  mehr Luft; qwen3.8-27b bis 16.581 Token. Der lmstudio-Adapter setzt in der
  Produktion **kein** `max_tokens` — der Fehler betraf nur den Testaufbau.
- **Ungeschützte Schleife auf Modulebene.** Das Messskript führte bei jedem
  Import einen zweiten kompletten Lauf gegen dasselbe Modell aus. Die
  Laufzeiten waren dadurch wertlos (dieselbe Frage einmal 27, einmal 167
  Sekunden) und eine Ergebnisdatei wurde überschrieben. Inhalte blieben
  unberührt.

## Offen

Das Kontextfenster von qwen3.6 steht auf 262144 statt der gewünschten 98304.
LM Studios Auto-Anpassung liest den angeforderten Wert beim Laden nicht — weder
aus dem Modell-Dialog noch aus `lms load -c`. Der Hebel ist `defaultContextLength`
in den App-Einstellungen, das auf `max` steht. Solange dort das Maximum gilt,
bleibt jede Vorgabe pro Modell wirkungslos.
