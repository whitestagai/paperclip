# LLM-Advisor: Marktdaten aus dem Skript statt Recherche im Agenten

**Datum:** 2026-08-20
**Status:** freigegeben, Umsetzung ausstehend
**Auslöser:** Schritt 3 des Routine-Briefs („Web-Recherche — deine Kernaufgabe") ist seit
dem Trägerwechsel am 31.07. nicht ausführbar
**Betroffen:** `~/.paperclip/scripts/llm-advisor/` (host-lokales Git-Repo, kein Remote),
Routine `666f3c66-e9e6-47a5-ad8a-96b86a8b21fb`, Agent LLM-Konfigurationsanalyst `efe7168d`

## Problem

Der Routine-Brief verlangt in Schritt 3 wörtlich „Suche per WebSearch nach NEUEN, für LM
Studio als MLX verfügbaren Modellen" und nennt das die Kernaufgabe des Agenten. Der
Träger läuft seit dem 31.07. auf `lmstudio_local` / `gemma-4-31b-it-mlx` und hat **kein
WebSearch-Werkzeug und keine Skills**. Er soll recherchieren und kann es nicht.

Das ist die beste verfügbare Erklärung für das Muster der Fehlalarm-Welle vom 07.08.: Die
Mail nannte Größenangaben zu drei HuggingFace-Repos, von denen eine um 2,5 GB danebenlag
(`Qwen3.6-27B-MLX-8bit` als „~27 GB" statt real 29,5 GB). Ein Modell, das eine
Rechercheaufgabe ohne Rechercheweg bekommt, füllt die Lücke aus dem Gedächtnis.

Dahinter liegt ein zweites, älteres Problem: Der Advisor hat **keine externe
Qualitätsachse**. Er sieht Fehlerzähler und Speicherbedarf, aber nichts darüber, ob ein
Zielmodell fachlich besser ist als das laufende. Deshalb hat er wiederholt
`google/gemma-4-12b` als Ziel vorgeschlagen — für die Sekretärin und für den CMO, beide
Male von Walter abgelehnt. Gegen eine externe Messung wäre der Vorschlag nie entstanden:
Artificial Analysis führt `gemma-4-12b` mit Intelligence Index **22,2** gegen **29,7** für
das laufende `gemma-4-31b`. Das ist ein sichtbares Downgrade.

**Nebenbefund, bereits behoben (20.08.):** Zwei von drei Läufen seit dem Trägerwechsel
starben am Wallclock-Kill-Switch (03.08. nach 14 Iterationen, 17.08. nach 11). Ursache war
ein fehlendes `adapterConfig.timeoutSec` — der lmstudio-Adapter liest dieses Feld, nicht
das vorhandene `timeoutMs`, und meldete selbst `timeoutConfigured: false`,
`timeoutSource: "default"`. Der Agent wurde am 30.07. per `agent-hires` als `process`
angelegt und bekam beim späteren Wechsel auf `lmstudio_local` nie die
lmstudio-Standardfelder; 22 von 25 lmstudio-Agenten tragen ein gültiges `timeoutSec`
(überwiegend 900, CHO 1800). Gesetzt auf
**1800** (wie CHO), weil die Läufe bei 300 s Budget nach 11–14 Iterationen noch nicht
fertig waren. Das ist Kontext für diese Spec, nicht ihr Gegenstand: **das Zeitbudget
bleibt knapp, deshalb darf die Lösung dem Agenten keine zusätzlichen Iterationen
aufbürden.**

## Ziel

Der Agent recherchiert nicht mehr selbst. Beide externen Quellen werden **vor** dem
Agentenlauf von `collect_ist_zustand.py` abgerufen und liegen fertig in
`state/ist-zustand.json`. Der Agent zitiert daraus — dieselbe Konstruktion, mit der
`evidence.py` die Telemetriezahlen bereits gegen freies Formulieren absichert.

**Erfolgskriterium:** Keine Zahl über ein Modell steht in einem Bericht, die nicht aus dem
JSON kopiert wurde, und die Zahl der Agenten-Iterationen sinkt gegenüber heute.

## Warum zwei Quellen und nicht eine

Sie beantworten verschiedene Fragen und sind nicht austauschbar:

| Quelle | beantwortet | taugt nicht für |
|---|---|---|
| Artificial Analysis (Free API) | „Wie gut ist Modell X gegenüber Modell Y?" | Was es Neues gibt; Geschwindigkeit und RAM auf eurer Hardware |
| Websuche-Dienst `:7789` | „Was ist überhaupt neu und als MLX verfügbar?" | belastbare Kennzahlen |

**Warum Artificial Analysis nicht über den Websuche-Dienst läuft:** Praktisch geprüft am
20.08. — der Dienst erreicht die AA-Modellseite und liefert 20.234 Zeichen, aber die
Textextraktion zerstört die Struktur. Aus `intelligenceIndex: 32.1290714769579` wird im
Fließtext `Intelligence # 6 / 135 32 Artificial Analysis Intelligence Index 4 out of 4
units`. Rang, Grundgesamtheit, gerundeter Index und eine Skalenangabe stehen ohne Trennung
nebeneinander. Für einen Advisor, dessen dokumentiertes Kernproblem erfundene Zahlen sind,
wäre das ein Rückschritt gegenüber strukturiertem JSON.

## Baustein 1 — `advisor/market.py`

Neues Modul im bestehenden Muster: es liefert Daten, `main()` komponiert.

| Funktion | Aufgabe |
|---|---|
| `fetch_aa(key, cache_pfad)` | `GET https://artificialanalysis.ai/api/v2/language/models/free`, Header `x-api-key`, paginiert (`pagination.has_more`), Seitendeckel gegen ein `has_more`, das nie endet. Antwort roh nach `state/aa-cache.json` mit Abrufdatum |
| `match_slug(lm_key, slugs, overrides)` | LM-Studio-Schlüssel → AA-Slug oder `None` |
| `fetch_web(frage, deadline)` | `POST http://127.0.0.1:7789/suche`, reicht `quellen` und `hinweis` unverändert durch |
| `market_report(...)` | komponiert das JSON-Fragment aus beidem |

### Zuordnung der Modellschlüssel

Normalisierung: Namensraum-Präfix abschneiden (`qwen/…`), Suffixe `-mlx`, `-mtplx`,
`-qat`, `-it`, `.gguf`, `@q4_k_m` entfernen, Punkte zu Bindestrichen. Am 20.08. gegen die
13 realen LM-Studio-Schlüssel geprüft: **10 Treffer**. Die drei Abweichungen kommen in die
Override-Tabelle:

```python
OVERRIDES = {
    "qwen/qwen3-coder-30b": "qwen3-coder-30b-a3b-instruct",
    "mistral-small-3.2-24b-instruct-2506": "mistral-small-3-2",
    "openbiollm-llama3-8b.gguf": None,   # bei AA nicht gelistet
}
```

**Kein Fuzzy-Matching.** Exakter Treffer, Override oder nichts. Eine falsche Zuordnung ist
gefährlicher als eine fehlende: `qwen3-coder-30b` versehentlich auf `qwen3-coder-480b-a35b`
gemappt ergäbe eine erfundene Zahl mit Autoritätsanschein — genau der Fehlertyp, den diese
Spec beseitigen soll. Nicht zugeordnete Schlüssel erscheinen in `nicht_gelistet`.

### Reasoning-Split

AA führt Reasoning- und Non-Reasoning-Varianten als getrennte Einträge mit erheblichem
Abstand (`gemma-4-31b`: 29,7 gegen 22,3; `qwen3.6-35b-a3b`: 32,1 gegen 24,6). Das Modul
zieht die Reasoning-Variante und schreibt die gewählte Variante in jedes Ergebnis, damit im
Bericht nie offenbleibt, welche Zahl gemeint ist.

## Baustein 2 — neuer Top-Level-Key in `ist-zustand.json`

```json
"model_market": {
  "status": "ok",
  "aa_stand": "2026-08-20",
  "quelle": "Artificial Analysis (Free API)",
  "modelle": {
    "gemma-4-31b-it-mlx": {
      "aa_slug": "gemma-4-31b", "variante": "Reasoning",
      "intelligence_index": 29.69, "coding_index": 43.43, "agentic_index": 14.38,
      "release_date": "2026-04-02"
    }
  },
  "nicht_gelistet": ["openbiollm-llama3-8b.gguf"],
  "suche": { "frage": "…", "abgerufen_am": "2026-08-20",
             "quellen": [ { "url": "…", "domain": "…", "text": "…" } ],
             "hinweis": null }
}
```

Felder, die der Free-Tier nicht liefert, stehen als `null` — nie geraten, nie aus einer
anderen Quelle ergänzt.

## Baustein 3 — `verify_market_claims()`

Gegenstück zu `evidence.verify_error_counts`. Prüft einen Berichtstext gegen
`model_market`: jede genannte Modell-Kennzahl muss dort stehen. Abweichung = ungültiger
Befund. Der Brief bekommt für Marktzahlen denselben Satz wie für Telemetriezahlen:
**schreibe keine Zahl, die du nicht aus dem JSON kopiert hast.**

## Baustein 4 — Ablehnungsliste `state/abgelehnte-modelle.json`

Eine externe Qualitätsachse empfiehlt beharrlich, was sie nicht wissen kann. `qwen3.8-27b`
steht bei AA auf Intelligence Index **52,0** — fast das Doppelte von `gemma-4-31b` — und
wurde trotzdem verworfen, weil die MLX-Variante den Denkmodus nicht abschalten lässt. Ohne
Gedächtnis empfiehlt der Advisor ihn jede Woche neu.

```json
[ { "modell": "qwen3.8-27b", "abgelehnt_am": "2026-08-17",
    "grund": "MLX-Variante lässt reasoning_effort=none nicht zu; nur auf der RTX brauchbar",
    "quelle": "project_qwen38_bewertung_und_adapter_reasoning_luecke" } ]
```

`market_report` markiert betroffene Modelle mit `abgelehnt` samt Grund. Der Brief: ein
abgelehntes Modell wird nicht vorgeschlagen, sondern höchstens erwähnt, wenn sich der
Ablehnungsgrund nachweislich erledigt hat.

## Baustein 5 — Brief-Neufassung und Routine-PATCH

Schritt 3 wird von „Suche per WebSearch" auf „Lies `model_market`" umgeschrieben. Danach
**zwingend** `PATCH /api/routines/666f3c66-e9e6-47a5-ad8a-96b86a8b21fb {"description": …}`
mit dem Dateiinhalt — die Routine führt eine Kopie des Briefs aus, nicht die Datei. Am
30.07. lief der Agent deshalb wochenlang mit einer Anleitung von vor dem Strukturfix.

## Fehlerverhalten: fail-closed

Kein Key, AA nicht erreichbar, `:7789` tot oder SearXNG unten → `status: "nicht_verfuegbar"`
mit Grund im Klartext. Der Brief sagt dann ausdrücklich: **keine Modellempfehlung ohne
Marktdaten** — der Bericht meldet, dass die Quelle fehlte.

Stilles Weiterlaufen ist die gefährlichste Variante: Genau daraus entstand die Lage, die
diese Spec behebt. Ein Agent mit unerfüllbarem Rechercheauftrag erfindet.

**Der Cache wird geschrieben, aber nie gelesen.** `state/aa-cache.json` hält fest, was beim
Lauf dastand — das ist Nachvollziehbarkeit, nicht Verfügbarkeit. Ein Lese-Fallback bei
Ausfall würde alte Zahlen als aktuelle ausgeben und damit exakt den Fehlertyp erzeugen, den
diese Spec beseitigt. Lieber keine Zahl als eine stille alte.

`collect_ist_zustand.py` darf an einem Ausfall der Marktdaten **nicht scheitern** — die
Telemetrie ist der wichtigere Teil und muss auch ohne Netz entstehen.

## Nicht-Ziele

- **Preise und Output-Speed aus AA werden nicht übernommen.** Sie messen gehostete
  Cloud-Endpunkte und sagen nichts über quantisiertes MLX auf Mac oder RTX. Geschwindigkeit
  und RAM bleiben Sache von `benchmark_candidate.sh`.
- **Kein automatischer Modellwechsel.** Der Advisor bleibt Melder.
- **Keine Änderung an `signals.py`.** `model_change_allowed=false` bleibt bindend; ein
  hoher Intelligence Index hebt eine Config-Ursache nicht auf.
- **Kein HTML-Scraping.** Bewusst verworfen zugunsten des Free-Tiers, obwohl das
  öffentliche SSR-HTML mehr Felder trägt.

## Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Quantisierung unsichtbar — AA misst Vollpräzision beim Provider | Brief weist Index als Vorauswahl aus, nicht als Messung; Bestätigung nur per Schatten-Benchmark |
| Free-Tier-Felder unbekannt bis zum ersten Abruf | fehlende Felder als `null`, nie geraten |
| Rate Limit 100/Tag | Cache in `state/`; Wochenroutine braucht wenige Requests |
| Attributionspflicht | Bericht nennt „Quelle: Artificial Analysis" mit Abrufdatum |
| Zusätzliche Laufzeit im Sammelskript | läuft außerhalb des Agenten-Wallclock; Websuche-Test 20.08.: 2,0 s |

## Testplan

Bestehende Suite: 111 Tests unter `.venv/bin/python` (3.9 — der Interpreter der Routine,
nicht das System-Python).

Neu in `tests/test_market.py`:
- `match_slug` für alle 13 realen Schlüssel, inklusive der drei Overrides und `None`
- kein Fuzzy-Treffer: ein unbekannter Schlüssel liefert `None`, nie einen Nachbarn
- Reasoning-Variante wird gewählt und ausgewiesen
- Pagination: `has_more` wird zu Ende gelesen
- fail-closed: fehlender Key, HTTP 401, HTTP 503, Timeout je `status: "nicht_verfuegbar"`
- `collect_ist_zustand` läuft vollständig durch, wenn beide Quellen ausfallen
- `verify_market_claims` schlägt bei abweichender Zahl an
- Ablehnungsliste markiert `qwen3.8-27b`

## Offene Punkte

1. **Der Free-API-Key fehlt.** Walter legt ihn an (kostenlos, artificialanalysis.ai →
   Anmelden → Key erstellen). Ablage analog `secrets/mailhub.env`, nicht im Klartext im
   Repo. Bis dahin meldet das Modul `nicht_verfuegbar` — implementierbar und testbar ist
   alles andere trotzdem.
2. **Welche Felder der Free-Tier wirklich liefert**, zeigt erst der erste echte Abruf. Die
   Doku nennt für Free nur „composite indices, pricing, performance" — ob
   `is_open_weights`, `context_window_tokens` und `huggingfaceUrl` dabei sind, ist offen.
   `huggingfaceUrl` wäre besonders wertvoll: an erfundenen Repo-Größen ist die 07.08.-Mail
   gescheitert.
3. **Wirkt `timeoutSec: 1800`?** Zeigt der nächste reguläre Lauf (Montag 07:00).
