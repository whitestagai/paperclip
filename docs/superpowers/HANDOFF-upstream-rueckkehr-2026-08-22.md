# Übergabe-Prompt: Rückkehr von unserem Paperclip-Fork zu Upstream

*Stand 2026-08-22. In neuen Chat kopieren, um nahtlos weiterzumachen.*

---

Unser Fork hängt **1.347 Commits hinter Upstream** (`paperclipai/paperclip`),
Fork-Punkt `0e1a58283` vom **07.05.2026**. Die Entscheidung ist gefallen:
**zurück zu Upstream**, nicht weiter forken. Dass das geht, ist nicht mehr
Theorie — es ist an einer Kopie der Produktivdaten durchgespielt.

## Der Befund, auf dem alles steht

**Die Upstream-Migrationen laufen sauber auf unsere Datenbank, ohne einen
einzigen verlorenen Datensatz.** Zweimal verifiziert:

| | gegen `master` | gegen Release `v2026.817.0` |
|---|---|---|
| angewandte Migrationen | 123 | 109 |
| Companies / Agenten | 3 / 47 | 3 / 47 |
| Issues / Kommentare | 7.303 / 18.801 | 7.307 / 18.808 |
| cost_events | 28.675 | 28.685 |

Der Grund, warum es klappt: Unsere zwei abweichenden Migrationen sind harmlos.
`0082_completion_requirement` fügt nur zwei Spalten zu `issues` hinzu (kollidiert
mit keiner Upstream-Migration), und `0083_slim_calypso` ist **zeichengleich** mit
Upstreams `0217_yielding_starbolt` — beide Seiten haben denselben ON-DELETE-Fix
unabhängig gebaut.

### ⚠️ Den Company-Export NICHT nehmen

Der naheliegende Weg (Company exportieren → in frische Instanz importieren) ist
eine Falle. `packages/shared/src/portability-fidelity.ts` listet explizit, was er
zurücklässt:

```
approvals_not_exported
cost_history_not_exported      ← unsere 28.685 cost_events
activity_history_not_exported
```

Und der Import vergibt neue UUIDs (`randomUUID()`), die Historie wäre danach auch
nicht nachtragbar. **Die Direktmigration der DB erhält alles.**

## Was schon steht

**Sandbox** unter `~/paperclip-upstream-sandbox`, auf dem Release-Tag
**`v2026.817.0`** (`213dabab`) — bewusst nicht `master`, weil Paperclip
Release-Kanäle fährt (canary→nightly→beta→stable) und `master` der
Entwicklungsstand ist.

- Server läuft auf **`:3101`** gegen `paperclip_sandbox` (Vollkopie der Produktivdaten)
- Produktiv läuft unangetastet weiter auf `:3100`
- Endpunkte verifiziert: `/api/companies`, `/api/agents`, `/api/issues` liefern identisch

**Alle Werkzeuge sind umschaltbar.** Die API-Adresse kommt jetzt aus
`PAPERCLIP_API_URL` (Default = bisheriges Verhalten, ohne Variable ändert sich
nichts). Damit ist der Cutover kein Big-Bang mehr — ein Dienst lässt sich
einzeln umhängen, indem seine launchd-plist die Variable setzt.

**Die Betriebsskripte sind im Repo.** 134 Dateien aus `~/.paperclip/scripts/`
liegen 1:1 gespiegelt unter `tools/`. Damit ist

```bash
diff -rq tools/ ~/.paperclip/scripts/ | grep -vE 'Only in|__pycache__|/venv/'
```

der Deploy-Drift-Test. Er fand beim ersten Lauf sofort, dass `seo-geo/cli.py`
live 12 Tage und 72 Zeilen voraus war.

### Commits dieser Session

Auf `feat/llm-usage-vault-export` (alle nach `fork` gepusht):

```
16ff9cdd7  security: Luna-Freigabe-Secret rotiert, Google-Key aus dem Code-Pfad
4d5510afa  fix(seo-geo): Deploy-Drift aufgeloest — Live-Stand war 12 Tage voraus
3c3042da7  chore(tools): fehlende Nicht-Code-Dateien nachgezogen
974e91777  chore(tools): 124 unversionierte Betriebsskripte ins Repo geholt
4bcf51105  feat(tools): Paperclip-Adresse ueber PAPERCLIP_API_URL konfigurierbar
```

Auf `master`: `684c5d90e` — fünf Dateien des Abschluss-Gates nachgereicht, die
seit dem 06.08. fehlten und `master` typecheck-untauglich machten.

Im Worktree `.worktrees/upstream-tier1` (Branch `feat/upstream-tier1-cherrypicks`,
gepusht, **nicht gemerged**): vier Upstream-Cherry-Picks als Vorrat —
Prozess-Confinement (#9504), Plugin-Autobuild (#8254), Migration-Safety-Lint,
externe Adapter-Overrides (#7394).

## Offene Punkte

**1. Google-Service-Account-Key ist NICHT rotiert.** ← nur von Hand
Key `f70191f34945820f4f29fcec3f6d7ce8b81cf47d` des Kontos
`seo-geo-reader@n8n-projekte-486711.iam.gserviceaccount.com` in der Google Cloud
Console widerrufen und neu ausstellen. Er lag vom 18.07. bis 21.08. im Klartext
neben dem Code. Verschoben ist er (`~/.paperclip/instances/default/secrets/`,
0600), aber gültig ist der alte weiterhin.

*(Das Luna-Freigabe-Secret ist erledigt — am 21.08. rotiert und verifiziert.)*

**2. Veraltetes `packages/adapter-utils/dist/` im Hauptrepo.**
Build-Artefakt vom 23.04., Quelle vom 13.06.; `execution-target` fehlt im `dist`
ganz. Das verdeckt die aktuellen Quellen und lässt `acpx-local` im Typecheck mit
neun Fehlern scheitern. Im frisch installierten Klon tritt es nicht auf.
Fix wäre `rm -rf packages/adapter-utils/dist` oder `pnpm build` — beides greift
in den Watch-Tree ein, in dem `ing.paperclip.dev` läuft, deshalb vorher den
launchd-Dienst stoppen.

**3. Sandbox abräumen oder behalten?**
Server `:3101` (PID wechselt), DB `paperclip_sandbox` auf `:54329`,
Klon `~/paperclip-upstream-sandbox`. Kostet Platz, sonst nichts.

**4. Der Tier-1-Worktree** liegt bereit, ist aber nicht nach `master` gemerged.
Entscheidung offen, ob wir ihn überhaupt noch brauchen — wenn der Umzug kommt,
sind drei der vier Picks im Release ohnehin enthalten.

## Nächster sinnvoller Schritt

Einen unkritischen Dienst probeweise auf die Sandbox umhängen (plist um
`PAPERCLIP_API_URL=http://127.0.0.1:3101` ergänzen) und ein paar Tage laufen
lassen. Das ist der erste echte Belastungstest — bisher ist nur gelesen worden.

## Fallen, die Zeit gekostet haben

- **`origin` ist Upstream (paperclipai), `fork` ist unser whitestagai-Remote.**
  Worktrees NIE mit Default-Basis anlegen — `EnterWorktree` zweigt von
  `origin/master` ab, also vom fremden Stand. Immer
  `git worktree add <pfad> -b <branch> master`.
- **Vor dem Serverstart gegen eine Datenkopie die Farm stilllegen**, sonst rennen
  47 Agenten auf echten Daten los (LLM-Calls, Mailversand):
  `UPDATE agents SET status='paused'; UPDATE routines SET status='paused';
  UPDATE plugins SET status='disabled';`
- **Der Dev-Runner ignoriert `PAPERCLIP_LISTEN_PORT`** und nimmt `:3101`.
- **`python3` ist hier Xcode-3.9.** seo-geo scheitert daran an der `X | None`-Syntax;
  die Suite braucht `~/.paperclip/scripts/seo-geo/venv/bin/python` (3.11).
- **n8n führt die Version unter `activeVersionId` aus, nicht den Draft.** Ein
  Secret muss in `workflow_entity` UND `workflow_history` ersetzt werden. Reload
  ohne Neustart geht über `tools/recovery/n8n_rest.py` (deactivate→activate).
- **Der Hauptcheckout wird von Paperclip-Agenten mitbenutzt.** Am 21.08. hat einer
  mitten in der Session den Branch gewechselt, ein Commit landete dadurch auf
  dessen Branch. Für längere Arbeiten in einem eigenen Worktree sitzen.
- **Ein `| head -N` hinter einem Serverstart killt den Server** (SIGPIPE). In eine
  Logdatei umleiten.

## Was der Fork uns kostet, solange er lebt

Zwei belegte Fälle, in denen wir Bugs neu diagnostiziert haben, die Upstream
längst behoben hatte:

- **pluginDbId / Tool-Routing**: Upstream `62863126a` (#5671) am 03.06., wir
  `af64a5f50` am 17.08. — 75 Tage Doppelarbeit.
- **`issue_comments` ON DELETE**: Upstream `44694328a` (#11331) am 13.08., wir
  `db9579add` am 06.08.

Vor jedem Kern-Debugging erst `git log origin/master --grep=` gegen die
betroffene Datei laufen lassen.
