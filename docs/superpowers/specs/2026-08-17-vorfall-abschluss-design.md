# Design: Vorfall-Abschluss — die geparkte Arbeit kommt zurück

- **Datum:** 2026-08-17
- **Status:** Entwurf zur Freigabe
- **Auslöser:** Seit dem 17.08. holt die Agenten-Selbstheilung gestrandete Agenten zurück (`docs/superpowers/specs/2026-07-24-agent-self-heal-design.md`, Baustein A). Der Agent lebt danach wieder — **seine Arbeit nicht.** Das Abschluss-Review formulierte es so: „Recovery parkt die Arbeit, Selbstheilung weckt den Arbeiter, niemand bringt beide zusammen."

## 1. Problem

Fällt ein Agent aus, passiert heute zweierlei, unabhängig voneinander:

1. Der **Recovery-Dienst** (`server/src/services/recovery/service.ts`) denkt in Issues. Er setzt das gestrandete Issue auf `blocked`, erzeugt ein Recovery-Issue (`originKind: "stranded_issue_recovery"`, `originId: <Quell-Issue>`) und hängt es als Blocker ein.
2. Die **Selbstheilung** (`server/src/services/recovery/agent-self-heal.ts`) denkt in Agenten. Sie klassifiziert die Störung, belebt bei transienten Fällen wieder und weckt den Agenten — **ohne Issue-Bezug**.

Ergebnis: Der Agent ist `idle` und läuft wieder, das Issue bleibt `blocked`. Schlimmer noch, es *sieht* geheilt aus — ein erfolgreicher Lauf schließt die Ledger-Zeile, der Wächter meldet Vollzug, und die Arbeit steht weiter still. Der Recovery-Kaskadenberg (~218 blockierte „Recover stalled…"-Issues) ist die historische Form desselben Problems.

## 2. Der entscheidende Fund: das Muster existiert bereits

Der Recovery-Dienst hat einen Abgleichlauf, der offene Recovery-Issues durchgeht und für jedes, **dessen Vorfall nicht mehr existiert**, den Blocker entfernt und das Issue stilllegt (`service.ts:2391`, `removeRecoveryBlockerFromSource` bei `:2302`). Er kennt heute nur eine Sorte Vorfall: Graph-Liveness-Befunde.

Es gibt also bereits eine „Ursache weg → Arbeit zurück"-Schleife samt Schutz gegen das Abräumen laufender Arbeit (`hasActiveRunForIssueId`, `:2319`). Sie weiß nur nichts davon, dass ein Agent gestrandet war, weil sein LLM starb.

**Daraus folgt der Zuschnitt dieses Entwurfs:** Die Selbstheilung braucht *keinen* eigenen Entblock-Pfad. Sie muss an dem vorhandenen teilnehmen. Ein zweiter Entblock-Pfad wäre exakt die Krankheit — zwei Mechanismen für dieselbe Sache —, nur eine Ebene tiefer.

## 3. Ziele / Nicht-Ziele

**Ziele**
- Ein Agent, der nach einer Störung nachweislich wieder liefert, bekommt seine geparkte Arbeit zurück, ohne dass ein Mensch eingreift.
- Das Recovery-Issue wird stillgelegt, statt einen Manager mit einer Störung zu beschäftigen, die sich selbst gelöst hat.
- Kein zweiter Entblock-Mechanismus. Die vorhandenen Operationen werden benutzt, nicht nachgebaut.

**Nicht-Ziele**
- Das gemeinsame Vorfall-Register beider Wächter (Entwurf „C"). Ziel, aber eigener Umbau — siehe §8.
- Die Menschen-Eskalation als Mail/Board-Vorgang (heute nur `activity_log` + Warn-Log).
- Baustein B, die Adapter-Härtung.
- Aufräumen des historischen Kaskadenbergs.

## 4. Entscheidungen (mit Walter abgestimmt, 17.08.)

| Frage | Entscheidung | Begründung |
|---|---|---|
| Wann gilt ein Agent als geheilt genug? | **Erst nach einem erfolgreichen Lauf.** | Live beobachtet: Wiederbelebung 1 scheiterte, erst Nummer 2 lief durch. Ein Revive allein ist kein Beleg. `resolved_at` im Ledger wird ausschliesslich von einem erfolgreichen (oder abgebrochenen) Lauf gesetzt — das ist das harte Signal. |
| Wem gehört die Arbeit, wenn der Manager schon eskaliert bekam? | **Ur-Agent bekommt sie zurück, Eskalation wird stillgelegt.** | Sonst bearbeitet ein Manager eine Störung, die sich selbst gelöst hat — die Kaskade, die uns 218 blockierte Issues eingebracht hat. |
| Was, wenn der Manager schon arbeitet? | **Nichts antasten**, beim nächsten Durchlauf erneut prüfen. | Die vorhandene `hasActiveRunForIssueId`-Sperre deckt genau das ab. |

## 5. Architektur

Ein neuer Abgleichschritt im Recovery-Dienst, im bestehenden Reconciliation-Pfad. Die Selbstheilung bleibt unangetastet — sie bekommt **keinen** Issue-Zugriff.

**Verbindungsglied** ist die schon vorhandene Kette:
`Recovery-Issue.originId` → Quell-Issue → `assigneeAgentId` → Agent → `agent_self_heal_ledger`.

Pro offenem `stranded_issue_recovery`-Issue:

1. **Auflösen.** `originId` → Quell-Issue laden. Kein Quell-Issue oder kein `assigneeAgentId` → überspringen.
2. **Heilung feststellen.** Gibt es für diesen Agenten eine Ledger-Zeile mit gesetztem `resolved_at`, die **nach** `createdAt` des Recovery-Issues liegt? Nur dann gilt: der Agent ist nach dem Stranden nachweislich wieder durchgelaufen.
3. **Aktive Arbeit schützen.** Läuft auf dem Recovery-Issue ein Lauf (`hasActiveRunForIssueId`), nichts tun — nächster Durchlauf entscheidet neu.
4. **Zurückgeben**, in dieser Reihenfolge:
   a. Blocker aus dem Quell-Issue entfernen (`removeRecoveryBlockerFromSource`).
   b. Recovery-Issue stilllegen, wie es der bestehende Pfad für erledigte Vorfälle tut.
   c. Ur-Agenten auf dem Quell-Issue wecken (`heartbeat.wakeup` mit `payload.issueId`), damit die Arbeit tatsächlich weitergeht statt nur formal frei zu sein.
5. **Protokollieren.** Jeder Schritt nach `activity_log`, `action: "recovery.incident_closed.*"`. Ein Wächter ohne Spur ist am 17.08. zweimal teuer geworden.

### Warum die Reihenfolge so ist

Entblocken **vor** dem Stilllegen: bricht Schritt b ab, ist das Issue frei und ein Mensch sieht ein verwaistes Recovery-Issue — die harmlosere Richtung. Umgekehrt wäre das Issue blockiert von einem stillgelegten Blocker, also unsichtbar tot. Wecken zuletzt, weil es der einzige Schritt mit Aussenwirkung ist.

## 6. Zuschnitt der Bausteine

| Einheit | Zweck | Abhängigkeiten |
|---|---|---|
| `decideIncidentClosure(input)` — **rein** | Bekommt Recovery-Erstellzeit, jüngstes `resolved_at` des Agenten, Flag „Lauf aktiv". Liefert `close` / `wait_active_run` / `not_healed` / `skip`. | keine |
| `findAgentHealingEvidence(db, agentId, since)` | Jüngstes `resolved_at` aus `agent_self_heal_ledger` nach `since`. | Drizzle |
| `reconcileHealedStrandedIssues(...)` | Der Durchlauf: laden, entscheiden, die drei Operationen ausführen, protokollieren. | die beiden obigen + vorhandene Recovery-Funktionen |

Die reine Entscheidungsfunktion getrennt zu halten hat sich bei `decideSelfHeal` bewährt: jeder Zweig ist ohne Datenbank und ohne Netz prüfbar.

## 7. Fehlerverhalten

- **Wecken schlägt fehl:** Blocker bleibt entfernt, Issue frei. Bewusst — ein freies Issue ohne Weckruf ist auffindbar, ein halb entblocktes nicht.
- **Ein Recovery-Issue wirft:** protokollieren, überspringen, die übrigen weiterverarbeiten (Muster aus `runAgentSelfHeal`).
- **Agent inzwischen wieder `error`:** `decideIncidentClosure` liefert `not_healed`, nichts passiert. Das Ledger hat dann eine neue offene Zeile.

## 8. Bekannte Grenze, die zu C führt

`resolveSelfHealLedgerForAgent` schliesst **alle** offenen Zeilen eines Agenten. Ein Agent mit zwei unabhängigen Störungen bekommt mit einem erfolgreichen Lauf beide zu — und damit potenziell zwei geparkte Issues zurück, obwohl nur eine Störung wirklich weg war. Am 17.08. live beobachtet: zwei Ledger-Zeilen für einen Vorfall, weil `process_lost` und `llm_error` verschiedene Fingerprints ergeben.

Für diesen Entwurf ist das eher hilfreich (im Zweifel kommt Arbeit zurück, statt liegenzubleiben). Es ist aber der Punkt, an dem das gemeinsame Vorfall-Register (C) ansetzen muss: ein Vorfall, auf den sich beide Wächter beziehen, statt zweier Zählweisen.

## 9. Testing

- **Rein (vitest):** `decideIncidentClosure` je Zweig — geheilt und frei, geheilt aber Lauf aktiv, nicht geheilt, Quell-Issue ohne Assignee, `resolved_at` älter als das Recovery-Issue (darf NICHT schliessen).
- **Integration (eingebettete Postgres):** die drei Hauptfälle end-to-end, inklusive der Prüfung, dass der Blocker wirklich aus `blockedByIssueIds` verschwindet und das Recovery-Issue stillgelegt ist.
- **Regression:** die bestehenden Recovery-Tests bleiben grün (`src/services/recovery/`, mit `--exclude "**/_paperclip.STALE-DISABLED-*/**"`).

## 10. Deploy

Wie Baustein A: Merge in den Arbeitsbranch des Hauptbaums, `launchctl kickstart -k gui/501/ing.paperclip.dev`, vorher prüfen dass keine `heartbeat_runs` laufen. Keine Migration nötig — es wird nur gelesen, was schon da ist.
