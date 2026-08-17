# Spec: Abschluss-Gate — `done` an verifizierte Work-Products binden

*Stand: 2026-07-13. Status: **UMGESETZT UND LIVE im Warn-Modus.** Teil (a) — Recovery-Prompt — ebenfalls live.*

## Umsetzungsstand (2026-07-13)

| Baustein | Datei | Status |
|---|---|---|
| Gate-Entscheidung (rein, 15 Tests) | `server/src/services/work-products/completion-gate.ts` | ✅ |
| Verifier (Datei/Commit/Dokument/URL, 15 Tests) | `server/src/services/work-products/verifier.ts` | ✅ |
| Laufzeit-Gate + Modus-Schalter | `server/src/services/work-products/gate-runtime.ts` | ✅ |
| Einhängung im `done`-Pfad | `server/src/services/issues.ts` (nach `assertTransition`) | ✅ |
| DB-Felder | Migration `0082_completion_requirement.sql` | ✅ angewandt |
| MCP-Tool `paperclipDeclareWorkProduct` | `packages/mcp-server/src/tools.ts` | ✅ |
| Serverseitige Verifikation beim Deklarieren | `server/src/routes/issues.ts` (POST work-products) | ✅ |

**Rollout:** `PAPERCLIP_COMPLETION_GATE=warn` + `PAPERCLIP_WORK_PRODUCT_ROOTS` (Paperclip-Repo + WHITESTAG-Vault)
im launchd-plist `ing.paperclip.dev`. Auf `enforce` schalten, sobald die Fehlalarmquote gemessen ist.

**End-to-End verifiziert** gegen echte DB + Dateisystem:
- nichts deklariert → blockiert
- Dokument statt Datei (der WHI-2519-Fehler) → blockiert („wrong location is not done")
- echte Datei + Commit `a0d45ff` → erlaubt
- erfundene Datei → `missing`

**Ein Bug, den erst der E2E-Lauf zeigte:** Commits wurden im *ersten* Root gesucht statt im Repo,
in dem die Datei liegt — ein Vault-Commit galt damit als nicht existent und echte Arbeit wurde als
`missing` gemeldet. Behoben (`rootOf`), Test hält es fest.

**Kernprinzip in der Umsetzung:** `healthStatus` ist kein Client-Feld. Die POST-Route überschreibt
jeden vom Agenten gesendeten Wert mit dem eigenen Prüfergebnis — ein Agent kann die Existenz seines
Artefakts nicht behaupten. Menschen (`actorUserId`) werden nie gegated.

## Befund (Diagnose WHI-2519)

Ein Agent kann ein Issue auf `done` setzen, ohne dass irgendetwas geprüft wird.

- **Statusübergang:** ein einziger `PATCH /issues/:id` mit `{status:"done", comment:"..."}`
  ([routes/issues.ts:2899](../../../server/src/routes/issues.ts#L2899) erzeugt den
  `source:"comment"`-Activity-Eintrag).
- **Einziger Guard:** `assertTransition` ([services/issues.ts:79](../../../server/src/services/issues.ts#L79))
  prüft nur, ob der Zielstatus ein bekannter String ist. Jeder Übergang aus jedem Status,
  durch jeden Agenten, ohne Artefakt, ohne Run.
- **`applyStatusSideEffects`** setzt lediglich `completedAt`.
- **`issue_work_products`** ist als Tabelle live, hat CRUD-Routen (`routes/issues.ts:1988/2020/2056/1700`)
  und wird von der UI gelesen — aber es gibt **kein MCP-Tool**, keine Skill-Erwähnung und
  **keine Verbindung zum `done`-Pfad**. Ergebnis: **0 Zeilen, jemals.**

**Der reale Fehlerfall war kein Lügen, sondern ein Zielort-Fehler.** Der CEO hat den Kurs
tatsächlich überarbeitet (37.831 Zeichen) — nur als Issue-Dokument in der DB statt als Datei
`WHITESTAG.ACADEMY/content/ki-datenschutz-dsgvo.md`. Run-Log: 4× `fs_read`, 0× `fs_write`.
Ein Gate, das nur auf Ehrlichkeit zielt, hätte hier nichts gefunden. Ein Gate, das fragt
*„liegt das Artefakt dort, wo der Auftrag es verlangt"*, hätte sofort angeschlagen.

**Angriffsfläche:** 210 `done`-Issues mit Recovery-Historie in 45 Tagen; in 96 Fällen hat ein
*anderer Agent als der Assignee* geschlossen. Wie viele davon am Ziel vorbeigeliefert haben,
ist nachträglich **nicht feststellbar** — weil `done` an nichts hängt. Das ist der Befund.

## Ziel

`done` ist nur erreichbar, wenn ein **registriertes Work-Product** existiert, das der Server
**selbst verifiziert** hat. Keine Selbstauskunft, kein Vertrauen in Kommentartext.

## Entwurf

### 1. Deklaration (Agentenseite)

Neues MCP-Tool `declare_work_product` (in `packages/mcp-server/src/tools.ts`), das die schon
vorhandene Route `POST /issues/:id/work-products` bedient. Der Agent deklariert **was er wo
erzeugt hat**:

| `type` | `provider` | `external_id` / `url` | Verifikation |
|---|---|---|---|
| `file` | `filesystem` / `git` | Pfad (+ optional Commit-SHA) | Datei existiert, ist nicht leer, ggf. im Commit enthalten |
| `commit` | `git` | SHA | Commit existiert, berührt die genannten Pfade |
| `document` | `paperclip` | `document_id` | Dokument existiert, `latest_body` nicht leer |
| `url` | `http` | URL | erreichbar (2xx), optional Inhalts-Assertion |

### 2. Verifikation (Serverseite)

Neuer Service `work-product-verifier.ts`. Setzt `issue_work_products.health_status`:
`verified` | `missing` | `unknown`. Läuft **synchron beim Deklarieren** und **erneut beim
`done`-Versuch** (kein Cachen von Vertrauen).

Wichtig: Die Verifikation prüft **Existenz und Ort**, nicht Qualität. Qualität bleibt Sache des
Lektorats/Reviews — das Gate soll nur den Fall „das Ding ist gar nicht da" ausschließen.

### 3. Das Gate

In `issueService.update`, vor `applyStatusSideEffects`:

```
if (ziel === "done" && issue.completionRequirement !== "none") {
  work = workProducts(issue.id).filter(is_primary)
  if (work.length === 0)                     → 422 "done requires a declared work product"
  if (work.some(w => w.health_status !== "verified")) → 422 "work product could not be verified: <ort>"
}
```

Neues Feld `issues.completion_requirement`: `work_product` (Default für Issues mit Deliverable)
| `none` (Diskussions-/Koordinations-Issues, Recovery-Issues selbst).

**Offene Entscheidung:** Default. `work_product` als Default für alle ist die strenge Variante
und wird anfangs Reibung erzeugen (Routine-Issues wie „Daily Health Briefing" haben kein
Datei-Artefakt). Vorschlag: Default `none`, aber der **Issue-Ersteller** (z.B. der Lektor, der
WHI-2519 anlegt) kann `work_product` mit erwartetem Typ+Ort setzen. Damit deklariert der
Auftraggeber das Ziel — nicht der Ausführende. Genau das hätte WHI-2519 gefangen.

### 4. Migration / Rollout

1. Feld + Verifier + MCP-Tool, Gate im **Warn-Modus** (loggt, blockt nicht) — eine Woche
   mitlaufen lassen, um die Fehlalarmquote zu messen.
2. Auswertung: wie viele `done`-Versuche hätten geblockt?
3. Erst dann hart schalten.

### 5. Was dadurch entfällt

Die ACADEMY-Insellösung (Prüfprofil „Runde 2: nie auf Selbstauskunft glauben" +
Pflicht-Zweitrunde in Routine `d7f2b01d`) wird dadurch nicht überflüssig — sie prüft *Qualität*.
Aber ihr Anteil „existiert die Änderung überhaupt" wandert in die Plattform und gilt dann für
alle Deliverable-Typen.

## Nicht in dieser Spec

- Qualitätsprüfung von Artefakten (bleibt Lektorat/Review).
- Rückwirkende Bereinigung der 210 `done`-Issues — ohne Artefaktbindung nicht automatisierbar;
  falls gewünscht, separat und stichprobenartig.
