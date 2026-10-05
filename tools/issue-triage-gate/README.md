# Issue-Triage-Gate — typisierte Entscheidungen mit Konfidenzschwelle

**Status: Werkzeug für den Trockenlauf. NICHT scharfgeschaltet.**
`triage.py` schreibt nichts, es liest nur und zeigt, was ein Gate entscheiden
würde. Es gibt keinen launchd-Job und keine Spiegelung nach `~/.paperclip/`.

## Wofür

Das Modell schreibt keinen Text, der danach geparst werden muss. Es erzeugt
genau **ein Token**, und ausgelesen wird die Wahrscheinlichkeitsverteilung
darüber. Die Masse auf den erlaubten Optionen wird renormiert. Damit kann das
Modell keine Option erfinden und keinen Formatfehler machen — und es fällt eine
**kalibrierbare Konfidenz** ab, an der ein Schwellwert hängen kann:

> Konfidenz über der Schwelle → automatisch entscheiden.
> Darunter → an einen Menschen, mit sichtbarer Neigung.

Das ist der nutzbare Kern der Jev-/System-One-Familie (SemIf liest Logits von
einem ungetunten Modell ab), hier **ohne neues Modell, ohne externen Dienst und
ohne Datenschutzfrage** — unsere LM-Studio-Modelle liefern die Logprobs selbst.

## Benutzen

```bash
python3 triage.py --limit 40                      # Schwelle 0.90
python3 triage.py --limit 40 --min-confidence 0.95
python3 -m pytest -q                              # 21 Tests
```

## Gemessen am 05.10.2026

40 blockierte Issues, `google/gemma-4-12b-qat` auf der RTX Pro 6000:

| Schwelle | automatisch | an den Menschen |
|---|---|---|
| 0.90 | 33 / 40 | 7 |
| 0.95 | 28 / 40 | 12 |

- **Latenz:** median 120 ms, max 163 ms
- **Masse auf erlaubten Optionen:** 1.000 (median) — keine Typfehler möglich
- **Stabilität:** 40 Issues zweimal durchgelaufen, **0 Entscheidungen gekippt**;
  derselbe Zustand 5× → identische Option, Konfidenz schwankt nur im Float-Rauschen
- Robust gegen Feldreihenfolge im Zustand

## Fallen

**★★ Ohne `reasoning_effort: "none"` kommen keine Logprobs.** Gemma 4 denkt im
GGUF, `content` bleibt leer — und dann ist auch `logprobs.content` leer. Das
sieht aus, als könnte das Modell keine Logprobs liefern. Der Schalter steht
deshalb fest in `build_request()`; nicht entfernen.

**★ Keinen Cache-Busting-Zeitstempel in den Zustand hängen.** Gemessen: derselbe
Issue kam mit Zeitstempel auf Konfidenz 0.89, ohne auf 0.82 — das kippt an der
Schwelle. Weil die Entscheidung bei gleicher Eingabe deterministisch ist, ist ein
Cache-Treffer erwünscht (Latenz 171 → 120 ms). `test_ask_sendet_genau_den_
gebauten_zustand` nagelt das fest.

**★ Eine Enthaltung ist kein Default.** `Decision.require_option()` wirft, wenn
nicht entschieden wurde. Wer den Rückgabewert ohne Prüfung weiterverwendet,
bekommt einen Fehler statt einer stillen Falschentscheidung.

**Zu wenig Masse auf den Optionen** (`min_mass`, Standard 0.5) heißt: das Modell
antwortet am Schema vorbei. Dann wird nicht geraten, sondern enthalten.

## Was NICHT belegt ist

**Die Qualität der Entscheidungen.** Es gibt keine gelabelten Fälle, also ist
nur belegt, dass das Verfahren trägt, stabil ist und die Konfidenz zwischen
klaren und unklaren Fällen trennt — **nicht, dass es richtig entscheidet.**
Vor dem Scharfschalten gehört eine Stichprobe von Hand gegengeprüft; der
Trockenlauf liefert genau die Liste dafür.

Die Optionen A/B/C stammen aus der bekannten Dreiteilung der `blocked`-Halde:
überholte Routine-Wiederholung (abbrechen), aufgegebenes Recovery-Symptom (Ziel
steht in `origin_id`), echte gestaute Arbeit (freigeben).
