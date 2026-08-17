# Prompt: Halluzinierte Abschlussmeldungen nach LLM-Abbruch (Flotten-Problem)

*Für eine spätere Session. Stand: 2026-07-12.*

---

In der Paperclip-Flotte gibt es ein Loch, das mir bei anderer Arbeit aufgefallen ist und
das ich untersuchen und schließen möchte:

**Ein Agent hat ein Issue als `done` gemeldet, mit einem detaillierten Erfolgsbericht —
und die Arbeit hatte nie stattgefunden.**

## Der konkrete Fall (als Reproduktionsfall)

- Issue **WHI-2519** („Kurs ki-datenschutz-dsgvo überarbeiten"), Assignee war der **CMO**.
- Sein Abschlusskommentar listet **acht behobene Mängel mit Häkchen**, inklusive
  erfundener Details: ein durchgehendes Fallbeispiel „Frau Müller, Inhaberin der
  Müller Druck, eine kleine Druckerei in Cottbus mit 5 Mitarbeitenden", sieben in
  `<details>` gewickelte Wissens-Checks, eine neue Datenschutz-Sektion nach Lektion 7.
- **Nichts davon existiert.** Die Datei
  `WHITESTAG-Vault/WHITESTAG.ACADEMY/content/ki-datenschutz-dsgvo.md` war unangetastet
  (git: keine Änderung; `grep -c "<details>"` → 0, `grep -c "tool_stand_gelesen"` → 0,
  `grep -c "^## Datenschutz"` → 0).
- Im selben Issue steht ein Recovery-Kommentar von Paperclip:
  `llm_error - LLM call failed: TypeError: fetch failed` → Recovery-Issue WHI-2521,
  Recovery-Owner CEO.

**Arbeitshypothese:** Der Agent formuliert erst seinen Plan (als Kommentar/Text), dann
bricht der LLM-Call weg. Was als Erfolgsmeldung stehenbleibt, ist die
**Absichtserklärung, nicht das Ergebnis** — und die Recovery-Mechanik schließt das
Issue trotzdem als `done` ab, statt es als unvollständig zu markieren.

## Was ich wissen will

1. **Ist die Hypothese richtig?** Lies den Recovery-Pfad im Server-Code
   (`server/src/recovery/`, `server/src/services/issues.ts`) und die Run-Logs
   (`~/.paperclip/instances/default/data/run-logs/<company>/<agent>/*.ndjson`) zu
   WHI-2519. Wo genau entsteht das `done`, obwohl der Lauf im `llm_error` endete?
2. **Wie verbreitet ist das?** Suche in der DB (embedded Postgres, Port 54329,
   `paperclip:paperclip`) nach weiteren Issues, die auf `done` stehen, obwohl im Lauf ein
   `llm_error` / Recovery protokolliert wurde. Wie viele „Erfolge" der letzten Wochen sind
   in Wahrheit keine?
3. **Wie schließen wir es?** Ein Agent kann seinen eigenen Erfolg nicht beurkunden. Ich
   erwarte einen Vorschlag, der ohne Vertrauen in die Selbstauskunft auskommt — z.B. ein
   Abschluss-Gate, das das behauptete Artefakt (Datei, Commit, Deliverable) tatsächlich
   prüft, bevor `done` gesetzt wird.

## Was schon getan ist (nicht doppelt machen)

Für die WHITESTAG.ACADEMY ist das Loch **lokal** gestopft, aber nur dort:

- Prüfprofil `WHITESTAG-Vault/Paperclip/_Meta/lektorat/pruefprofile/kurs.md` enthält jetzt
  den Abschnitt „Runde 2: Nachbesserungen NIE auf Selbstauskunft glauben" — der Lektor-Agent
  (`3deca5b4-af4b-43a3-93f4-2cc4fc1bd08d`) liest in Runde 2 die Datei neu ein und prüft
  jeden Mangel daran nach, statt dem Bericht des Autors zu glauben.
- Die ACADEMY-Routine (`d7f2b01d-8b4b-454c-907d-15156e255ac4`) hat einen Schritt 4:
  Der CEO gibt nie auf Selbstauskunft frei, sondern schickt jede gemeldete Nachbesserung
  zwingend in eine zweite Lektorats-Runde.

Das ist eine **Insellösung für einen Deliverable-Typ**. Die Frage ist, ob so etwas in die
Plattform gehört, statt in jedes Prüfprofil einzeln.

## Kontext, den du brauchst

- Betroffener Agent im Fall: CMO. Der Fehler ist aber vermutlich nicht agentenspezifisch.
- Erfahrungswert: Recovery-Kaskaden sind in dieser Flotte ein wiederkehrendes Thema
  (`maxIterations`-Cap, `MAX_RECOVERY_IN_PLACE_CYCLES=3` in `recovery/service.ts`).
- Dev-Server läuft als launchd `ing.paperclip.dev` auf :3100 — **nicht** in den Watch-Tree
  mergen, Neustart nur per `launchctl kickstart -k gui/501/ing.paperclip.dev`.

Fang mit der Diagnose an (Punkt 1 und 2), bevor du irgendetwas änderst. Ich will erst
wissen, wie groß das Loch ist.
