# Agent Nightly Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paperclip-Agenten lernen nachts kontinuierlich — Online-Recherche schreibt Domain-Wissen, Vault-Maintainer destilliert Lessons aus Reibungs-Runs. Beides landet im Obsidian-Vault unter `Paperclip/Skill-Wissen/` + `Paperclip/Agenten/{whitestag,health}/<slug>/`. Skills selbst bleiben eingefroren.

**Architecture:** Bash-Trigger-Script (`agent-learning-trigger.sh`) wird via launchd zu drei festen Zeitpunkten (01:00, 02:00, So 03:00) ausgelöst. Es liest eine YAML-Config, fragt die Paperclip-REST-API ab, erzeugt Issues mit Templates und weist sie den Agenten zu. Agenten schreiben den Vault, Vault-Maintainer syncht Context-Bundles zurück in `instructions/`-Ordner. Alle Logik konfigurierbar via `~/.paperclip/instances/default/agent-learning.config.yaml`.

**Tech Stack:** Bash 5+, `jq`, `yq` (mikefarah), `curl`, Paperclip REST API (`http://127.0.0.1:3100`), launchd, Obsidian-Vault-Filesystem.

**Spec:** [`docs/superpowers/specs/2026-05-11-agent-nightly-learning-design.md`](../specs/2026-05-11-agent-nightly-learning-design.md)

---

## File Structure (Übersicht)

Im Repo (versioniert):
```
scripts/agent-learning/
  README.md
  install.sh                                  # symlinkt nach ~/.paperclip/scripts/, kopiert Config-Template
  uninstall.sh
  agent-learning-trigger.sh                   # Haupt-Entry, Modes: knowledge | lessons | decay
  lib/
    config.sh                                 # load_config(), validate_config()
    paperclip_api.sh                          # paperclip_*() Wrapper um curl
    vault_ops.sh                              # vault_*() für Filesystem
    slug.sh                                   # slug_from_name(), update_slug_index()
    rotation.sh                               # weekday_domains()
    bundle_sync.sh                            # sync_bundle_to_agent()
    decay.sh                                  # archive_old_files(), patch_memory_index()
    status.sh                                 # append_status_entry()
  templates/
    issue_knowledge.md
    issue_lessons.md
    memory_initial.md
    agents_md_snippet.md
    config.example.yaml
  launchd/
    de.whitestag.agent-learning.knowledge.plist
    de.whitestag.agent-learning.lessons.plist
    de.whitestag.agent-learning.decay.plist
  tests/
    test_slug.sh
    test_rotation.sh
    test_config.sh
    test_idempotency.sh
    test_decay.sh
```

Auf der Maschine (User-Files, nicht im Repo):
```
~/.paperclip/scripts/                         # Symlinks zu scripts/agent-learning/
  agent-learning-trigger.sh
  lib/ ...
~/.paperclip/instances/default/
  agent-learning.config.yaml                  # einmalig vom Template kopiert
~/Library/LaunchAgents/
  de.whitestag.agent-learning.{knowledge,lessons,decay}.plist
```

Im Vault (Source-of-Truth des Wissens):
```
/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/
  Skill-Wissen/<domain>/{MEMORY.md, *.md, _archive/}
  Agenten/_index.md                            # Slug ↔ UUID ↔ Company
  Agenten/_status.md                           # Lauf-Log
  Agenten/{whitestag,health}/<slug>/{MEMORY.md, lessons/, references/}
```

---

## Task 0: Preconditions — Dependencies & API verifizieren

**Files:**
- (keine Änderungen, nur Verifikation)

- [ ] **Step 1: Verify required CLI tools are installed**

Run:
```bash
command -v jq && command -v yq && command -v curl
yq --version  # muss mikefarah/yq sein, nicht python-yq. Erwartet: "yq (https://github.com/mikefarah/yq/) version vX.Y.Z"
```
Expected: alle drei Pfade ausgegeben, yq-Version mit `mikefarah` in Output.

Wenn fehlt: `brew install jq yq` und nochmal.

- [ ] **Step 2: Verify Paperclip API is reachable**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3100/api/companies
```
Expected: `200`.

Wenn nicht `200`: `launchctl list | grep paperclip` → prüfen ob `ing.paperclip.dev` läuft.

- [ ] **Step 3: Verify all three company IDs and resolve any mismatch**

Run:
```bash
curl -s http://127.0.0.1:3100/api/companies | jq -r '.[] | "\(.id)\t\(.name)"'
```
Expected: drei Companies mit IDs. Notiere für jede den Namen:
- `9cebf3cf-efe8-4597-a400-f06488900a87` → erwartet "WHITESTAG"
- `158c4959-4973-4cb0-8066-55ec0f35625e` → erwartet "Health Insights" o.ä.
- `0e426844-309c-4528-9aa5-90ff76790a51` → erwartet "Clara Sound"

**Wenn ein Mapping nicht passt:** Pause, Spec-Konstanten-Tabelle korrigieren und Plan-Konstanten unten anpassen, bevor weiter.

- [ ] **Step 4: Verify Online-Recherche and Vault-Maintainer agent IDs**

Run:
```bash
curl -s http://127.0.0.1:3100/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/agents | jq -r '.[] | select(.name | test("Online-Recherche|Vault-Maintainer")) | "\(.id)\t\(.name)\t\(.adapterType)"'
```
Expected: zwei Zeilen:
```
d80fe6b9-b2ac-4d58-8525-8bbbb1d0caf7  Online-Recherche   claude_local
3067ea1d-5050-4032-aff5-1f759f544160  Vault-Maintainer   claude_local
```

Beide aktuell auf `claude_local`. Vault-Maintainer wird in Task 1 zurück auf `lmstudio_local` gestellt.

- [ ] **Step 5: Verify vault is mounted**

Run:
```bash
ls /Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/ | head -5
```
Expected: existierende Files/Folders sichtbar (z.B. `_README.md`, `Projekte`, `Recherche`).

Wenn `No such file or directory`: Vault einbinden, dann nochmal.

---

## Task 1: Precondition — Vault-Maintainer Adapter zurück auf lmstudio_local

**Files:**
- Modify (via API): Agent `3067ea1d-5050-4032-aff5-1f759f544160` (Vault-Maintainer)

- [ ] **Step 1: Snapshot current Vault-Maintainer config**

Run:
```bash
curl -s http://127.0.0.1:3100/api/agents/3067ea1d-5050-4032-aff5-1f759f544160 > /tmp/vm-before.json
jq '{adapterType, adapterConfig}' /tmp/vm-before.json
```
Expected: `adapterType: "claude_local"` und ein `adapterConfig` mit `model: "claude-sonnet-..."` o.ä.

Snapshot bleibt unter `/tmp/vm-before.json` als Rollback-Referenz.

- [ ] **Step 2: Look up a working lmstudio agent config as template**

Run:
```bash
curl -s http://127.0.0.1:3100/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/agents \
  | jq -r '.[] | select(.adapterType == "lmstudio_local") | {name, adapterConfig}' | head -40
```
Expected: ein paar lmstudio-Agenten mit `model`, `endpoint`, `apiKey`, `graceSec`, `maxTurnsPerRun`-Felder. Notiere die Felder, die wir übernehmen.

- [ ] **Step 3: Build the PATCH payload**

Schreibe Payload nach `/tmp/vm-patch.json`:
```json
{
  "adapterType": "lmstudio_local",
  "adapterConfig": {
    "model": "<gleiches Modell wie andere lmstudio-Agenten>",
    "endpoint": "<gleicher endpoint>",
    "apiKey": "<gleicher apiKey>",
    "graceSec": 15,
    "timeoutSec": 900,
    "maxTurnsPerRun": 50,
    "instructionsFilePath": "<aus /tmp/vm-before.json übernehmen>",
    "instructionsRootPath": "<aus /tmp/vm-before.json übernehmen>",
    "instructionsEntryFile": "AGENTS.md",
    "instructionsBundleMode": "managed",
    "dangerouslySkipPermissions": true
  }
}
```

Die `model`/`endpoint`/`apiKey`-Werte aus Step 2 nehmen. Die `instructions*`-Pfade aus `/tmp/vm-before.json` übernehmen — die ändern sich nicht.

- [ ] **Step 4: Apply the PATCH**

Run:
```bash
curl -s -X PATCH http://127.0.0.1:3100/api/agents/3067ea1d-5050-4032-aff5-1f759f544160 \
  -H "Content-Type: application/json" \
  -d @/tmp/vm-patch.json | jq '{adapterType, "model": .adapterConfig.model}'
```
Expected: `adapterType: "lmstudio_local"` und das erwartete `model`.

- [ ] **Step 5: Smoke-test the Vault-Maintainer**

Erzeuge ein leichtes Test-Issue in WHITESTAG, assigne es Vault-Maintainer:
```bash
curl -s -X POST http://127.0.0.1:3100/api/companies/9cebf3cf-efe8-4597-a400-f06488900a87/issues \
  -H "Content-Type: application/json" \
  -d '{"title":"Smoke-Test: lmstudio adapter","body":"Bitte antworte mit einem Satz: \"Ich laufe.\"","assignedAgentId":"3067ea1d-5050-4032-aff5-1f759f544160"}' \
  | jq '{id, status}'
```
Expected: Issue-ID + Status. Beobachte über die nächsten 1-2 Minuten via `tail -f ~/.paperclip/instances/default/logs/server.log` oder UI, ob ein Run startet und durchläuft (kein `process_lost`, kein Adapter-Error).

- [ ] **Step 6: Commit der Aktion (kein Code-Change, aber Audit-Eintrag)**

Diese Task ändert keinen Code im Repo, sondern Live-Config. Trotzdem als Marker im Plan vermerken — der Subagent oder Walter dokumentiert den Schritt im Issue-Tracker bzw. im nächsten Chatverlauf.

Wenn alles passt: weiter zu Task 2.

---

## Task 2: Repo-Setup — Verzeichnisstruktur unter `scripts/agent-learning/`

**Files:**
- Create: `scripts/agent-learning/README.md`
- Create: `scripts/agent-learning/lib/.gitkeep`
- Create: `scripts/agent-learning/templates/.gitkeep`
- Create: `scripts/agent-learning/launchd/.gitkeep`
- Create: `scripts/agent-learning/tests/.gitkeep`

- [ ] **Step 1: Create base folders**

Run:
```bash
mkdir -p scripts/agent-learning/{lib,templates,launchd,tests}
touch scripts/agent-learning/{lib,templates,launchd,tests}/.gitkeep
```

- [ ] **Step 2: Write README**

Create `scripts/agent-learning/README.md`:
```markdown
# Agent Nightly Learning

Implementation of the nightly learning loops for Paperclip agents.
See spec: `docs/superpowers/specs/2026-05-11-agent-nightly-learning-design.md`

## Layout

- `agent-learning-trigger.sh` — main entry (modes: knowledge | lessons | decay)
- `lib/` — shared Bash functions
- `templates/` — issue-body / memory / agents.md snippets
- `launchd/` — three plists, one per schedule (01:00 / 02:00 / Sun 03:00)
- `tests/` — sandboxed Bash tests for pure-logic functions

## Install

```bash
./install.sh
```

This symlinks scripts to `~/.paperclip/scripts/`, copies the config template
to `~/.paperclip/instances/default/agent-learning.config.yaml` (only if missing),
and installs launchd plists.

## Uninstall

```bash
./uninstall.sh
```

Removes symlinks and launchd plists. Config and vault contents are kept.
```

- [ ] **Step 3: Commit**

```bash
git add scripts/agent-learning/
git commit -m "feat(agent-learning): scaffold directory structure"
```

---

## Task 3: Config-Template & Validation

**Files:**
- Create: `scripts/agent-learning/templates/config.example.yaml`
- Create: `scripts/agent-learning/lib/config.sh`
- Create: `scripts/agent-learning/tests/test_config.sh`

- [ ] **Step 1: Write the failing test**

Create `scripts/agent-learning/tests/test_config.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/config.sh"

# Test 1: valid template parses
CONFIG_FILE="$HERE/../templates/config.example.yaml" load_config
[[ "$CONFIG_VAULT_ROOT" == "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault" ]] \
  || { echo "FAIL: vault root mismatch ($CONFIG_VAULT_ROOT)"; exit 1; }
[[ "$CONFIG_COMPANIES_WHITESTAG_ID" == "9cebf3cf-efe8-4597-a400-f06488900a87" ]] \
  || { echo "FAIL: whitestag id mismatch"; exit 1; }

# Test 2: missing file errors clearly
if CONFIG_FILE=/tmp/does-not-exist.yaml load_config 2>/dev/null; then
  echo "FAIL: load_config should fail on missing file"; exit 1
fi

# Test 3: weekday rotation accessible
domains=$(weekday_domains "mon")
[[ "$domains" == *"n8n"* ]] || { echo "FAIL: monday should include n8n ($domains)"; exit 1; }

echo "OK: test_config.sh"
```

```bash
chmod +x scripts/agent-learning/tests/test_config.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./scripts/agent-learning/tests/test_config.sh`
Expected: FAIL with `source: lib/config.sh: No such file or directory` (or similar — file doesn't exist yet).

- [ ] **Step 3: Write the config template**

Create `scripts/agent-learning/templates/config.example.yaml`:
```yaml
# Agent Learning Loops — Config
# Walter darf hier alles anpassen. Trigger-Script liest die Datei bei jedem Lauf frisch.

vault:
  root: /Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault
  knowledge_dir: Paperclip/Skill-Wissen
  agents_dir: Paperclip/Agenten

paperclip:
  api_base: http://127.0.0.1:3100

companies:
  whitestag:
    id: 9cebf3cf-efe8-4597-a400-f06488900a87
    slug: whitestag
  health:
    id: 158c4959-4973-4cb0-8066-55ec0f35625e
    slug: health

agents:
  online_recherche:
    id: d80fe6b9-b2ac-4d58-8525-8bbbb1d0caf7
    slug: online-recherche
  vault_maintainer:
    id: 3067ea1d-5050-4032-aff5-1f759f544160
    slug: vault-maintainer

knowledge_loop:
  schedule: "0 1 * * *"
  assignee_agent_id: d80fe6b9-b2ac-4d58-8525-8bbbb1d0caf7
  max_turns_per_run: 30
  timeout_sec: 600
  rotation:
    mon: [n8n, photoshop]
    tue: [blender, mistika-vr]
    wed: [adobe-cep, premiere]
    thu: [pyatv, homepod-bridge]
    fri: [claude-api, paperclip-sdk]
    sat: []
    sun: []

lessons_loop:
  schedule: "0 2 * * *"
  assignee_agent_id: 3067ea1d-5050-4032-aff5-1f759f544160
  lookback_hours: 24
  trigger_run_statuses: [failed, errored]
  always_pickup_marker: "LESSON-CANDIDATE"
  max_runs_per_sweep: 10
  selection_order: newest_first
  skip_if_empty: true

decay_pass:
  schedule: "0 3 * * 0"
  knowledge_archive_after_days: 180
  lessons_archive_after_days: 90

budgets:
  memory_md_max_lines: 200
  knowledge_files_per_domain: 30
  lessons_per_agent: 50
  context_bundle_max_tokens: 5000

domains:
  n8n:
    title: "n8n Workflow Automation"
    sources:
      - https://docs.n8n.io/release-notes/
      - https://community.n8n.io/c/announcements/
    skill_refs: [whitestag-n8n-workflow]
  photoshop:
    title: "Adobe Photoshop"
    sources:
      - https://helpx.adobe.com/photoshop/release-note/photoshop-release-notes.html
    skill_refs: [adobe-automation]
  blender:
    title: "Blender 3D"
    sources:
      - https://www.blender.org/download/releases/
    skill_refs: [blender-scripting]
  mistika-vr:
    title: "Mistika VR"
    sources: []
    skill_refs: [mistika-vr-pipeline]
  adobe-cep:
    title: "Adobe CEP / UXP Extensions"
    sources:
      - https://github.com/Adobe-CEP/CEP-Resources/releases
    skill_refs: [adobe-automation]
  premiere:
    title: "Adobe Premiere Pro"
    sources:
      - https://helpx.adobe.com/premiere-pro/release-note/premiere-pro-release-notes.html
    skill_refs: []
  pyatv:
    title: "pyatv — Apple TV / HomePod direkt-streamen"
    sources:
      - https://pyatv.dev/
      - https://github.com/postlund/pyatv/releases
    skill_refs: []
  homepod-bridge:
    title: "HomePod-Bridge (Paperclip → HomePod Voice)"
    sources: []
    skill_refs: []
  claude-api:
    title: "Anthropic Claude API & SDK"
    sources:
      - https://docs.anthropic.com/en/release-notes
    skill_refs: [claude-api]
  paperclip-sdk:
    title: "Paperclip Plugin SDK"
    sources: []
    skill_refs: [paperclip, paperclip-create-plugin]
```

- [ ] **Step 4: Write the config loader**

Create `scripts/agent-learning/lib/config.sh`:
```bash
# Loaded via `source`. Exports CONFIG_* environment variables.
# Default config path: ~/.paperclip/instances/default/agent-learning.config.yaml
# Override via env var CONFIG_FILE.

load_config() {
  local config_file="${CONFIG_FILE:-$HOME/.paperclip/instances/default/agent-learning.config.yaml}"
  if [[ ! -f "$config_file" ]]; then
    echo "ERROR: config file not found: $config_file" >&2
    return 1
  fi

  export CONFIG_FILE="$config_file"
  export CONFIG_VAULT_ROOT=$(yq '.vault.root' "$config_file")
  export CONFIG_VAULT_KNOWLEDGE_DIR=$(yq '.vault.knowledge_dir' "$config_file")
  export CONFIG_VAULT_AGENTS_DIR=$(yq '.vault.agents_dir' "$config_file")
  export CONFIG_PAPERCLIP_API_BASE=$(yq '.paperclip.api_base' "$config_file")
  export CONFIG_COMPANIES_WHITESTAG_ID=$(yq '.companies.whitestag.id' "$config_file")
  export CONFIG_COMPANIES_HEALTH_ID=$(yq '.companies.health.id' "$config_file")
  export CONFIG_ONLINE_RECHERCHE_ID=$(yq '.agents.online_recherche.id' "$config_file")
  export CONFIG_VAULT_MAINTAINER_ID=$(yq '.agents.vault_maintainer.id' "$config_file")
  export CONFIG_KNOWLEDGE_MAX_TURNS=$(yq '.knowledge_loop.max_turns_per_run' "$config_file")
  export CONFIG_KNOWLEDGE_TIMEOUT_SEC=$(yq '.knowledge_loop.timeout_sec' "$config_file")
  export CONFIG_LESSONS_LOOKBACK_HOURS=$(yq '.lessons_loop.lookback_hours' "$config_file")
  export CONFIG_LESSONS_MAX_RUNS=$(yq '.lessons_loop.max_runs_per_sweep' "$config_file")
  export CONFIG_LESSONS_MARKER=$(yq '.lessons_loop.always_pickup_marker' "$config_file")
  export CONFIG_LESSONS_SKIP_IF_EMPTY=$(yq '.lessons_loop.skip_if_empty' "$config_file")
}

weekday_domains() {
  # $1 = mon|tue|wed|thu|fri|sat|sun
  local day="$1"
  yq ".knowledge_loop.rotation.${day}[]" "${CONFIG_FILE}" 2>/dev/null || true
}

domain_title() {
  yq ".domains.${1}.title" "${CONFIG_FILE}"
}

domain_sources() {
  yq ".domains.${1}.sources[]" "${CONFIG_FILE}" 2>/dev/null || true
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./scripts/agent-learning/tests/test_config.sh`
Expected: `OK: test_config.sh`

- [ ] **Step 6: Commit**

```bash
git add scripts/agent-learning/templates/config.example.yaml scripts/agent-learning/lib/config.sh scripts/agent-learning/tests/test_config.sh
git commit -m "feat(agent-learning): config template and loader"
```

---

## Task 4: Slug-Helper

**Files:**
- Create: `scripts/agent-learning/lib/slug.sh`
- Create: `scripts/agent-learning/tests/test_slug.sh`

- [ ] **Step 1: Write the failing test**

Create `scripts/agent-learning/tests/test_slug.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/slug.sh"

assert_eq() { [[ "$1" == "$2" ]] || { echo "FAIL: expected '$2' got '$1'"; exit 1; }; }

assert_eq "$(slug_from_name 'Online-Recherche')"   "online-recherche"
assert_eq "$(slug_from_name 'Vault-Maintainer')"   "vault-maintainer"
assert_eq "$(slug_from_name 'Bild & Video')"       "bild-und-video"
assert_eq "$(slug_from_name 'CTO')"                "cto"
assert_eq "$(slug_from_name '  Online   Recherche  ')" "online-recherche"
assert_eq "$(slug_from_name 'Müll-Räumer')"        "muell-raeumer"

echo "OK: test_slug.sh"
```

```bash
chmod +x scripts/agent-learning/tests/test_slug.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./scripts/agent-learning/tests/test_slug.sh`
Expected: FAIL — file doesn't exist.

- [ ] **Step 3: Implement slug_from_name**

Create `scripts/agent-learning/lib/slug.sh`:
```bash
# Convert a display name to a filesystem-safe slug.
# Examples:
#   "Bild & Video"       → "bild-und-video"
#   "Müll-Räumer"        → "muell-raeumer"
#   "  Online Recherche " → "online-recherche"

slug_from_name() {
  local name="$1"
  # German umlauts → ASCII
  name=$(echo "$name" | sed \
    -e 's/ä/ae/g' -e 's/ö/oe/g' -e 's/ü/ue/g' -e 's/ß/ss/g' \
    -e 's/Ä/Ae/g' -e 's/Ö/Oe/g' -e 's/Ü/Ue/g')
  # & → "und"
  name=$(echo "$name" | sed 's/&/und/g')
  # lowercase
  name=$(echo "$name" | tr '[:upper:]' '[:lower:]')
  # everything non-alphanumeric → "-"
  name=$(echo "$name" | sed 's/[^a-z0-9]/-/g')
  # collapse multiple dashes
  name=$(echo "$name" | sed 's/--*/-/g')
  # trim leading/trailing dashes
  name=$(echo "$name" | sed 's/^-//' | sed 's/-$//')
  echo "$name"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./scripts/agent-learning/tests/test_slug.sh`
Expected: `OK: test_slug.sh`

- [ ] **Step 5: Commit**

```bash
git add scripts/agent-learning/lib/slug.sh scripts/agent-learning/tests/test_slug.sh
git commit -m "feat(agent-learning): slug helper"
```

---

## Task 5: Paperclip-API-Wrapper

**Files:**
- Create: `scripts/agent-learning/lib/paperclip_api.sh`

(Keine separate Test-Suite — wird in End-to-End-Test in Task 16 verifiziert, da API-Calls Live-State berühren.)

- [ ] **Step 1: Implement the wrappers**

Create `scripts/agent-learning/lib/paperclip_api.sh`:
```bash
# Wrapper around curl + jq for Paperclip REST API.
# Requires CONFIG_PAPERCLIP_API_BASE to be set (via load_config).

paperclip_get() {
  # $1 = path (e.g. /api/companies)
  curl -sS -f "${CONFIG_PAPERCLIP_API_BASE}$1"
}

paperclip_post_json() {
  # $1 = path, $2 = JSON body string
  curl -sS -f -X POST "${CONFIG_PAPERCLIP_API_BASE}$1" \
    -H "Content-Type: application/json" \
    -d "$2"
}

paperclip_patch_json() {
  curl -sS -f -X PATCH "${CONFIG_PAPERCLIP_API_BASE}$1" \
    -H "Content-Type: application/json" \
    -d "$2"
}

paperclip_list_agents() {
  # $1 = company id
  paperclip_get "/api/companies/$1/agents"
}

paperclip_create_issue() {
  # $1 = company id, $2 = title, $3 = body, $4 = assignedAgentId
  local payload
  payload=$(jq -n \
    --arg t "$2" --arg b "$3" --arg a "$4" \
    '{title:$t, body:$b, assignedAgentId:$a}')
  paperclip_post_json "/api/companies/$1/issues" "$payload"
}

paperclip_list_issues() {
  # $1 = company id, $2 = optional `?since=...` query (already URL-encoded)
  paperclip_get "/api/companies/$1/issues${2:-}"
}

paperclip_list_runs() {
  # Returns runs across all companies; filter client-side via jq.
  # $1 = optional query string (e.g. ?status=failed&since=...)
  paperclip_get "/api/runs${1:-}"
}

paperclip_get_run_activity() {
  # $1 = run id
  paperclip_get "/api/runs/$1/activity"
}

paperclip_get_issue_comments() {
  # $1 = issue id
  paperclip_get "/api/issues/$1/comments"
}
```

- [ ] **Step 2: Quick smoke test**

Run:
```bash
bash -c "
source scripts/agent-learning/lib/config.sh
source scripts/agent-learning/lib/paperclip_api.sh
CONFIG_FILE=scripts/agent-learning/templates/config.example.yaml load_config
paperclip_list_agents \$CONFIG_COMPANIES_WHITESTAG_ID | jq 'length'
"
```
Expected: Zahl > 5 (Anzahl der WHITESTAG-Agenten, derzeit 24).

- [ ] **Step 3: Commit**

```bash
git add scripts/agent-learning/lib/paperclip_api.sh
git commit -m "feat(agent-learning): paperclip API wrappers"
```

---

## Task 6: Slug-Index aus Paperclip-API generieren

**Files:**
- Modify: `scripts/agent-learning/lib/slug.sh` (add `update_slug_index`)
- Create: `scripts/agent-learning/tests/test_slug_index.sh`

- [ ] **Step 1: Write a sandboxed test**

Create `scripts/agent-learning/tests/test_slug_index.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/slug.sh"

# Sandbox a fake vault
SANDBOX=$(mktemp -d)
trap "rm -rf $SANDBOX" EXIT
mkdir -p "$SANDBOX/Paperclip/Agenten"

# Fake API response for two companies
WHITESTAG_AGENTS='[
  {"id":"aaa","name":"Online-Recherche"},
  {"id":"bbb","name":"Vault-Maintainer"},
  {"id":"ccc","name":"Bild & Video"}
]'
HEALTH_AGENTS='[
  {"id":"ddd","name":"CHO"},
  {"id":"eee","name":"Datenauswerter"}
]'

write_slug_index "$SANDBOX/Paperclip/Agenten/_index.md" \
  "whitestag" "$WHITESTAG_AGENTS" \
  "health" "$HEALTH_AGENTS"

grep -q "online-recherche.*aaa.*whitestag" "$SANDBOX/Paperclip/Agenten/_index.md" \
  || { echo "FAIL: online-recherche entry missing"; cat "$SANDBOX/Paperclip/Agenten/_index.md"; exit 1; }
grep -q "bild-und-video.*ccc" "$SANDBOX/Paperclip/Agenten/_index.md" \
  || { echo "FAIL: bild-und-video entry missing"; exit 1; }
grep -q "datenauswerter.*eee.*health" "$SANDBOX/Paperclip/Agenten/_index.md" \
  || { echo "FAIL: datenauswerter entry missing"; exit 1; }

echo "OK: test_slug_index.sh"
```

```bash
chmod +x scripts/agent-learning/tests/test_slug_index.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./scripts/agent-learning/tests/test_slug_index.sh`
Expected: FAIL — `write_slug_index` doesn't exist yet.

- [ ] **Step 3: Add write_slug_index to slug.sh**

Append to `scripts/agent-learning/lib/slug.sh`:
```bash

# Write _index.md mapping (slug ↔ uuid ↔ company)
# Variadic: write_slug_index <output-file> <company-slug-1> <agents-json-1> <company-slug-2> <agents-json-2> ...
write_slug_index() {
  local out="$1"; shift
  {
    echo "# Agent Slug-Index"
    echo
    echo "Auto-generiert von \`agent-learning-trigger.sh\`. Bitte nicht von Hand editieren —"
    echo "wird beim nächsten Lauf überschrieben."
    echo
    echo "| Slug | UUID | Company |"
    echo "|---|---|---|"
    while [[ $# -gt 0 ]]; do
      local company_slug="$1"; shift
      local agents_json="$1"; shift
      echo "$agents_json" | jq -r '.[] | [.name, .id] | @tsv' \
        | while IFS=$'\t' read -r name id; do
          local slug
          slug=$(slug_from_name "$name")
          echo "| ${slug} | \`${id}\` | ${company_slug} |"
        done
    done
  } > "$out"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./scripts/agent-learning/tests/test_slug_index.sh`
Expected: `OK: test_slug_index.sh`

- [ ] **Step 5: Commit**

```bash
git add scripts/agent-learning/lib/slug.sh scripts/agent-learning/tests/test_slug_index.sh
git commit -m "feat(agent-learning): generate slug index from paperclip api"
```

---

## Task 7: Vault-Operationen

**Files:**
- Create: `scripts/agent-learning/lib/vault_ops.sh`
- Create: `scripts/agent-learning/templates/memory_initial.md`
- Create: `scripts/agent-learning/tests/test_vault_ops.sh`

- [ ] **Step 1: Memory-Initial-Template**

Create `scripts/agent-learning/templates/memory_initial.md`:
```markdown
# Memory Index — {{AGENT_NAME}}

*Dieser Index wird vom Vault-Maintainer nächtlich gepflegt. Walter darf manuelle Edits machen — sie bleiben erhalten (mtime-Vergleich beim Decay-Pass).*

## Eigene Lessons

*(noch keine — werden vom Reibungs-Sweep nach Fehl-Runs angelegt)*

## Skill-Wissen (verlinkt)

*(noch keine Domains verlinkt — werden vom Knowledge-Loop nach erstem Recherche-Pass eingetragen)*

## Referenzen

- [Quellen](references/quellen.md)
```

- [ ] **Step 2: Write the failing test**

Create `scripts/agent-learning/tests/test_vault_ops.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/vault_ops.sh"

SANDBOX=$(mktemp -d)
trap "rm -rf $SANDBOX" EXIT
export CONFIG_VAULT_ROOT="$SANDBOX"
export CONFIG_VAULT_KNOWLEDGE_DIR="Paperclip/Skill-Wissen"
export CONFIG_VAULT_AGENTS_DIR="Paperclip/Agenten"

# vault_ensure_knowledge_domain
vault_ensure_knowledge_domain "n8n" "n8n Workflow Automation"
[[ -f "$SANDBOX/Paperclip/Skill-Wissen/n8n/MEMORY.md" ]] \
  || { echo "FAIL: n8n MEMORY.md missing"; exit 1; }
[[ -d "$SANDBOX/Paperclip/Skill-Wissen/n8n/_archive" ]] \
  || { echo "FAIL: n8n _archive/ missing"; exit 1; }

# Idempotency: second call must not overwrite content
echo "## Manual edit" >> "$SANDBOX/Paperclip/Skill-Wissen/n8n/MEMORY.md"
vault_ensure_knowledge_domain "n8n" "n8n Workflow Automation"
grep -q "Manual edit" "$SANDBOX/Paperclip/Skill-Wissen/n8n/MEMORY.md" \
  || { echo "FAIL: manual edit lost on second ensure"; exit 1; }

# vault_ensure_agent
TEMPLATE="$HERE/../templates/memory_initial.md"
vault_ensure_agent "whitestag" "online-recherche" "Online-Recherche" "$TEMPLATE"
[[ -f "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/MEMORY.md" ]] \
  || { echo "FAIL: agent MEMORY.md missing"; exit 1; }
[[ -d "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/lessons" ]] \
  || { echo "FAIL: lessons dir missing"; exit 1; }
[[ -d "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/references" ]] \
  || { echo "FAIL: references dir missing"; exit 1; }
grep -q "Online-Recherche" "$SANDBOX/Paperclip/Agenten/whitestag/online-recherche/MEMORY.md" \
  || { echo "FAIL: agent name not substituted"; exit 1; }

echo "OK: test_vault_ops.sh"
```

```bash
chmod +x scripts/agent-learning/tests/test_vault_ops.sh
```

- [ ] **Step 3: Run test to verify it fails**

Run: `./scripts/agent-learning/tests/test_vault_ops.sh`
Expected: FAIL — `vault_ops.sh` doesn't exist.

- [ ] **Step 4: Implement vault_ops.sh**

Create `scripts/agent-learning/lib/vault_ops.sh`:
```bash
# Filesystem operations on the Obsidian vault.
# Requires CONFIG_VAULT_ROOT, CONFIG_VAULT_KNOWLEDGE_DIR, CONFIG_VAULT_AGENTS_DIR.

vault_check_mounted() {
  [[ -d "$CONFIG_VAULT_ROOT" ]] || {
    echo "ERROR: vault not mounted at $CONFIG_VAULT_ROOT" >&2
    return 1
  }
}

vault_ensure_knowledge_domain() {
  # $1 = domain slug, $2 = domain title
  local domain="$1" title="$2"
  local dir="$CONFIG_VAULT_ROOT/$CONFIG_VAULT_KNOWLEDGE_DIR/$domain"
  mkdir -p "$dir/_archive"
  if [[ ! -f "$dir/MEMORY.md" ]]; then
    cat > "$dir/MEMORY.md" <<EOF
# Memory Index — ${title}

*Domain-Index, wird vom Online-Recherche-Agent nächtlich gepflegt.*

## Aktive Einträge

*(noch keine)*

## Archiv

Siehe \`_archive/\`.
EOF
  fi
}

vault_ensure_agent() {
  # $1 = company slug, $2 = agent slug, $3 = agent display name, $4 = path to memory template
  local co="$1" ag="$2" name="$3" tmpl="$4"
  local dir="$CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR/$co/$ag"
  mkdir -p "$dir/lessons/_archive" "$dir/references"
  if [[ ! -f "$dir/MEMORY.md" ]]; then
    sed "s/{{AGENT_NAME}}/${name}/g" "$tmpl" > "$dir/MEMORY.md"
  fi
  if [[ ! -f "$dir/references/quellen.md" ]]; then
    cat > "$dir/references/quellen.md" <<EOF
# Externe Quellen — ${name}

*(URLs, Doku-Pointers — wird über Zeit vom Agent ergänzt)*
EOF
  fi
}

vault_status_append() {
  # $1 = section header line (e.g. "## 2026-05-12 01:00 — Recherche-Pass")
  # stdin = body lines
  local status="$CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR/_status.md"
  if [[ ! -f "$status" ]]; then
    cat > "$status" <<EOF
# Agent Learning — Lauf-Status

Auto-generiert. Jeder Trigger-Lauf appendet hier einen Eintrag.

EOF
  fi
  {
    echo
    echo "$1"
    cat
  } >> "$status"
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./scripts/agent-learning/tests/test_vault_ops.sh`
Expected: `OK: test_vault_ops.sh`

- [ ] **Step 6: Commit**

```bash
git add scripts/agent-learning/lib/vault_ops.sh scripts/agent-learning/templates/memory_initial.md scripts/agent-learning/tests/test_vault_ops.sh
git commit -m "feat(agent-learning): vault filesystem operations"
```

---

## Task 8: Issue-Body-Templates

**Files:**
- Create: `scripts/agent-learning/templates/issue_knowledge.md`
- Create: `scripts/agent-learning/templates/issue_lessons.md`
- Create: `scripts/agent-learning/templates/agents_md_snippet.md`

- [ ] **Step 1: Knowledge-Issue-Body-Template**

Create `scripts/agent-learning/templates/issue_knowledge.md`:
```markdown
**Domain:** {{DOMAIN_TITLE}}
**Quellen:**
{{SOURCES_LIST}}

**Vault-Pfad für diese Domain:**
`{{VAULT_DOMAIN_PATH}}`

## Auftrag

Recherchiere, was sich bei {{DOMAIN_TITLE}} seit dem letzten Update geändert hat. Konzentriere dich auf Neuerungen mit **operativem Impact** — also Features/Changes, die wir in unseren Workflows nutzen könnten oder die bestehende Workflows brechen.

## Schreib-Regeln

1. **Dedup zuerst:** Liste existierende Files unter `{{VAULT_DOMAIN_PATH}}`. Wenn ein Topic schon existiert → bestehende Datei updaten (im Frontmatter `updated: {{TODAY}}` setzen), keine neue Datei anlegen.
2. **Quality-Gate:** Schreibe nur, wenn die Information *non-obvious / surprising / actionable* ist. Generische Release-Listen ohne operative Konsequenz nicht schreiben — Issue auf `done` mit Comment "no new actionable knowledge".
3. **Frontmatter-Pflicht:**
   ```yaml
   ---
   name: <Titel>
   description: <ein Satz>
   type: knowledge
   domain: {{DOMAIN_SLUG}}
   agent: online-recherche
   created: {{TODAY}}
   sources:
     - <url>
   ---
   ```
4. **MEMORY.md aktualisieren:** Nach jedem Knowledge-File-Write den Domain-Index in `{{VAULT_DOMAIN_PATH}}/MEMORY.md` aktualisieren (neuen Eintrag in "Aktive Einträge").

## Constraints

- Max {{MAX_TURNS}} Turns, Max {{TIMEOUT_SEC}} Sek.
- Web-Recherche erlaubt (WebFetch/WebSearch).
- Wenn unsicher → kein Eintrag besser als ein schlechter Eintrag.
- Bei Tool-Error oder unklarer Anweisung: Comment mit `LESSON-CANDIDATE: <kurz>` setzen, der nächtliche Reibungs-Sweep destilliert daraus eine Lesson.
```

- [ ] **Step 2: Lessons-Issue-Body-Template**

Create `scripts/agent-learning/templates/issue_lessons.md`:
```markdown
**Reibungs-Runs vom {{YESTERDAY}}:**

{{RUN_LIST}}

## Auftrag

Für jeden Reibungs-Run oben:

1. Hole das vollständige Activity-Log via `GET /api/runs/<run-id>/activity` und Comments via `GET /api/issues/<issue-id>/comments`.
2. Destilliere in **3-5 Sätzen**: *Was ist passiert? Warum? Was sollte der Agent beim nächsten Mal anders machen?*
3. Schreibe das Lesson nach `{{VAULT_LESSONS_PATH_PATTERN}}` mit Frontmatter:
   ```yaml
   ---
   name: <kurzer Titel>
   description: <ein Satz>
   type: lesson
   agent: <agent-slug>
   company: <company-slug>
   created: {{TODAY}}
   sources:
     - run://<run-id>
   ---
   ```
4. Aktualisiere die Agent-MEMORY.md (`{{VAULT_AGENT_PATH_PATTERN}}/MEMORY.md`) — füge Lesson-Eintrag oben in der Lessons-Liste hinzu.

## Sub-Step nach allen Lessons: Context-Bundle-Sync

Für jeden Agent in (whitestag, health):

- Kopiere `<vault-agent-pfad>/MEMORY.md` → `<instructions-path>/MEMORY.md`
- Erstelle `<instructions-path>/recent-lessons.md`: Top-5 Lessons der letzten 14 Tage, Volltext
- Erstelle `<instructions-path>/relevant-knowledge.md`: Headlines (aus `Skill-Wissen/<domain>/MEMORY.md`, nur "Aktive Einträge"-Liste, kein Volltext) für jede verlinkte Domain im Agent-MEMORY

## Constraints

- Wenn `trigger_run_statuses` leer ist und keine Reibungs-Runs gefunden → Issue auf `done` mit Comment "no friction yesterday, nothing to learn".
- Max {{MAX_RUNS}} Runs pro Sweep (neueste zuerst).
- Vault nicht gemounted → Issue auf `blocked` mit Comment "Vault not mounted, skipping". Kein Schreiben.
- Quality-Gate gilt auch hier: keine generischen Lessons ("Aufgabe ist gescheitert" ohne Lerngehalt) — solche Runs werden ohne Eintrag übersprungen.
```

- [ ] **Step 3: AGENTS.md-Snippet**

Create `scripts/agent-learning/templates/agents_md_snippet.md`:
```markdown

---

## Gedächtnis & Lernen

Beim Task-Start: lies `MEMORY.md` und `recent-lessons.md` in deinem Instructions-Ordner. Diese enthalten dein gesammeltes Wissen aus vorherigen Tasks und nächtlicher Recherche.

Wenn ein Eintrag aus `relevant-knowledge.md` für deine aktuelle Task relevant ist, lade die vollständige Datei aus dem Vault nach:
`/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Skill-Wissen/<domain>/...`

Wenn du beim Task auf eine echte Reibung stößt (Tool-Error, unklare Anweisung, fehlende Dependency), markiere das im Run-Comment explizit als `LESSON-CANDIDATE: <kurz>` — der nächtliche Reibungs-Sweep destilliert daraus eine Lesson.
```

- [ ] **Step 4: Commit**

```bash
git add scripts/agent-learning/templates/issue_knowledge.md scripts/agent-learning/templates/issue_lessons.md scripts/agent-learning/templates/agents_md_snippet.md
git commit -m "feat(agent-learning): issue body and agents.md templates"
```

---

## Task 9: Rotation-Helper

**Files:**
- Create: `scripts/agent-learning/lib/rotation.sh`
- Create: `scripts/agent-learning/tests/test_rotation.sh`

- [ ] **Step 1: Write the failing test**

Create `scripts/agent-learning/tests/test_rotation.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/rotation.sh"

assert_eq() { [[ "$1" == "$2" ]] || { echo "FAIL: expected '$2' got '$1'"; exit 1; }; }

# Bash date format: %u → 1=Mon ... 7=Sun
assert_eq "$(weekday_short 1)" "mon"
assert_eq "$(weekday_short 5)" "fri"
assert_eq "$(weekday_short 7)" "sun"

# today's weekday-short is non-empty and in mon..sun
TODAY=$(weekday_short_today)
echo "Today is: $TODAY"
case "$TODAY" in
  mon|tue|wed|thu|fri|sat|sun) ;;
  *) echo "FAIL: unexpected weekday $TODAY"; exit 1 ;;
esac

echo "OK: test_rotation.sh"
```

```bash
chmod +x scripts/agent-learning/tests/test_rotation.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./scripts/agent-learning/tests/test_rotation.sh`
Expected: FAIL.

- [ ] **Step 3: Implement rotation.sh**

Create `scripts/agent-learning/lib/rotation.sh`:
```bash
weekday_short() {
  # $1 = ISO weekday number (1=Mon..7=Sun)
  case "$1" in
    1) echo "mon" ;;
    2) echo "tue" ;;
    3) echo "wed" ;;
    4) echo "thu" ;;
    5) echo "fri" ;;
    6) echo "sat" ;;
    7) echo "sun" ;;
    *) return 1 ;;
  esac
}

weekday_short_today() {
  weekday_short "$(date +%u)"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./scripts/agent-learning/tests/test_rotation.sh`
Expected: `OK: test_rotation.sh`

- [ ] **Step 5: Commit**

```bash
git add scripts/agent-learning/lib/rotation.sh scripts/agent-learning/tests/test_rotation.sh
git commit -m "feat(agent-learning): weekday rotation helper"
```

---

## Task 10: Idempotency-Check

**Files:**
- Create: `scripts/agent-learning/lib/idempotency.sh`
- Create: `scripts/agent-learning/tests/test_idempotency.sh`

- [ ] **Step 1: Write the failing test**

Create `scripts/agent-learning/tests/test_idempotency.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/idempotency.sh"

# Mock paperclip_list_issues for the test
paperclip_list_issues() {
  # Fake response: one issue with the same title, created 6h ago
  local now_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local six_hours_ago=$(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '6 hours ago' +%Y-%m-%dT%H:%M:%SZ)
  cat <<EOF
[
  {"id":"abc","title":"Recherche: n8n — Neuerungen seit 2026-05-05","createdAt":"$six_hours_ago"},
  {"id":"def","title":"Some other issue","createdAt":"$now_iso"}
]
EOF
}

# Test: duplicate within 24h → returns true (skip)
if issue_already_exists_today "dummy-company-id" "Recherche: n8n — Neuerungen seit 2026-05-05"; then
  echo "OK: dedup detected"
else
  echo "FAIL: dedup not detected"; exit 1
fi

# Test: unique title → returns false (proceed)
if issue_already_exists_today "dummy-company-id" "Recherche: photoshop — Neuerungen seit 2026-05-05"; then
  echo "FAIL: false positive on unique title"; exit 1
else
  echo "OK: unique title accepted"
fi

echo "OK: test_idempotency.sh"
```

```bash
chmod +x scripts/agent-learning/tests/test_idempotency.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./scripts/agent-learning/tests/test_idempotency.sh`
Expected: FAIL — `idempotency.sh` doesn't exist.

- [ ] **Step 3: Implement idempotency.sh**

Create `scripts/agent-learning/lib/idempotency.sh`:
```bash
# Returns 0 (true) if an issue with this title was created in the last 24h
# in the given company. Used to avoid duplicate issues on re-trigger.
# Depends on paperclip_list_issues being defined.

issue_already_exists_today() {
  local company_id="$1" title="$2"
  local cutoff
  cutoff=$(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)
  local match_count
  match_count=$(paperclip_list_issues "$company_id" | jq --arg t "$title" --arg cutoff "$cutoff" \
    '[.[] | select(.title == $t and .createdAt >= $cutoff)] | length')
  [[ "$match_count" -gt 0 ]]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./scripts/agent-learning/tests/test_idempotency.sh`
Expected: `OK: dedup detected` / `OK: unique title accepted` / `OK: test_idempotency.sh`

- [ ] **Step 5: Commit**

```bash
git add scripts/agent-learning/lib/idempotency.sh scripts/agent-learning/tests/test_idempotency.sh
git commit -m "feat(agent-learning): 24h issue title idempotency"
```

---

## Task 11: Trigger-Script Entry-Point + Knowledge-Mode

**Files:**
- Create: `scripts/agent-learning/agent-learning-trigger.sh`

(End-to-End-Test mit Live-API in Task 16. Hier nur Dry-Run-Smoke-Test.)

- [ ] **Step 1: Implement the entry-point**

Create `scripts/agent-learning/agent-learning-trigger.sh`:
```bash
#!/usr/bin/env bash
# Agent Nightly Learning Trigger
# Usage: agent-learning-trigger.sh <knowledge|lessons|decay> [--dry-run]

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/lib/config.sh"
source "$HERE/lib/paperclip_api.sh"
source "$HERE/lib/vault_ops.sh"
source "$HERE/lib/slug.sh"
source "$HERE/lib/rotation.sh"
source "$HERE/lib/idempotency.sh"

MODE="${1:-}"; shift || true
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "Usage: $0 <knowledge|lessons|decay> [--dry-run]" >&2
  exit 2
fi

log() { echo "[$(date +%H:%M:%S)] $*"; }

load_config
vault_check_mounted

# Render template: $1 = template path, additional args are KEY=value pairs.
# Uses pure-Bash parameter expansion — handles multi-line values and quotes safely.
render_template() {
  local tmpl="$1"; shift
  local content
  content=$(cat "$tmpl")
  for kv in "$@"; do
    local k="${kv%%=*}" v="${kv#*=}"
    content="${content//\{\{${k}\}\}/${v}}"
  done
  printf '%s' "$content"
}

case "$MODE" in
  knowledge)
    log "Knowledge-Loop starting"
    today_short=$(weekday_short_today)
    today_iso=$(date +%Y-%m-%d)
    domains=$(weekday_domains "$today_short")
    if [[ -z "$domains" ]]; then
      log "No domains scheduled for $today_short — exiting clean."
      exit 0
    fi
    for domain in $domains; do
      title=$(domain_title "$domain")
      sources_list=$(domain_sources "$domain" | sed 's/^/- /')
      vault_path="${CONFIG_VAULT_ROOT}/${CONFIG_VAULT_KNOWLEDGE_DIR}/${domain}"

      vault_ensure_knowledge_domain "$domain" "$title"

      issue_title="Recherche: ${title} — Stand ${today_iso}"
      if issue_already_exists_today "$CONFIG_COMPANIES_WHITESTAG_ID" "$issue_title"; then
        log "Skip $domain — issue with same title exists in last 24h."
        continue
      fi

      body=$(render_template "$HERE/templates/issue_knowledge.md" \
        "DOMAIN_TITLE=${title}" \
        "DOMAIN_SLUG=${domain}" \
        "SOURCES_LIST=${sources_list}" \
        "VAULT_DOMAIN_PATH=${vault_path}" \
        "TODAY=${today_iso}" \
        "MAX_TURNS=${CONFIG_KNOWLEDGE_MAX_TURNS}" \
        "TIMEOUT_SEC=${CONFIG_KNOWLEDGE_TIMEOUT_SEC}")

      if [[ "$DRY_RUN" -eq 1 ]]; then
        log "DRY-RUN: would create issue '$issue_title' in WHITESTAG, assigned to online-recherche"
        echo "--- BODY ---"; echo "$body"; echo "--- END ---"
      else
        result=$(paperclip_create_issue "$CONFIG_COMPANIES_WHITESTAG_ID" \
          "$issue_title" "$body" "$CONFIG_ONLINE_RECHERCHE_ID")
        issue_id=$(echo "$result" | jq -r '.id')
        log "Created knowledge issue: $issue_id ($domain)"
      fi
    done

    if [[ "$DRY_RUN" -eq 0 ]]; then
      vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Recherche-Pass ($today_short)" \
        <<EOF
- Domains: $(echo $domains | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
EOF
    fi
    log "Knowledge-Loop done."
    ;;

  lessons)
    log "Lessons-Loop placeholder — see Task 12"
    ;;
  decay)
    log "Decay-Pass placeholder — see Task 13"
    ;;
  *)
    echo "Unknown mode: $MODE" >&2; exit 2 ;;
esac
```

```bash
chmod +x scripts/agent-learning/agent-learning-trigger.sh
```

- [ ] **Step 2: Dry-run smoke test with the example config**

Run:
```bash
CONFIG_FILE=scripts/agent-learning/templates/config.example.yaml \
  ./scripts/agent-learning/agent-learning-trigger.sh knowledge --dry-run
```
Expected (Inhalt variiert je Wochentag): mindestens eine `DRY-RUN: would create issue 'Recherche: ...'`-Zeile, gefolgt von Body-Output. Keine Errors. Falls Wochentag = Samstag/Sonntag → `No domains scheduled for sat/sun`.

- [ ] **Step 3: Commit**

```bash
git add scripts/agent-learning/agent-learning-trigger.sh
git commit -m "feat(agent-learning): trigger entry-point + knowledge mode"
```

---

## Task 12: Trigger-Script Lessons-Mode

**Files:**
- Modify: `scripts/agent-learning/agent-learning-trigger.sh` (replace lessons placeholder)

- [ ] **Step 1: Replace the lessons-mode placeholder**

In `scripts/agent-learning/agent-learning-trigger.sh`, replace the `lessons)` case block with:

```bash
  lessons)
    log "Lessons-Loop starting"
    today_iso=$(date +%Y-%m-%d)
    yesterday_iso=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d 'yesterday' +%Y-%m-%d)
    cutoff_iso=$(date -u -v-${CONFIG_LESSONS_LOOKBACK_HOURS}H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
      || date -u -d "${CONFIG_LESSONS_LOOKBACK_HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)

    # Build status list as query: ?status=failed&status=errored&since=<iso>
    statuses=$(yq '.lessons_loop.trigger_run_statuses[]' "$CONFIG_FILE")
    query=""
    for s in $statuses; do
      query="${query}&status=${s}"
    done
    query="?since=${cutoff_iso}${query}"

    # Fetch + filter by company (whitestag + health) + sort newest first
    runs_json=$(paperclip_list_runs "$query" \
      | jq --arg wh "$CONFIG_COMPANIES_WHITESTAG_ID" --arg he "$CONFIG_COMPANIES_HEALTH_ID" \
          --argjson max "$CONFIG_LESSONS_MAX_RUNS" \
          '[.[] | select(.companyId == $wh or .companyId == $he)]
           | sort_by(.createdAt) | reverse | .[0:$max]')

    run_count=$(echo "$runs_json" | jq 'length')
    if [[ "$run_count" -eq 0 && "$CONFIG_LESSONS_SKIP_IF_EMPTY" == "true" ]]; then
      log "No friction runs in last ${CONFIG_LESSONS_LOOKBACK_HOURS}h — skipping."
      if [[ "$DRY_RUN" -eq 0 ]]; then
        vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Reibungs-Sweep" \
          <<EOF
- skipped — no friction runs in last ${CONFIG_LESSONS_LOOKBACK_HOURS}h
EOF
      fi
      exit 0
    fi

    # Build run list for issue body
    run_list=$(echo "$runs_json" | jq -r '.[] | "- Run `\(.id[:8])…` — Agent `\(.agentName // "?")` — Company `\(.companyName // "?")` — Status `\(.status)` — Issue `\(.issueTitle // "?")`"')

    issue_title="Lessons aus Reibungs-Runs vom ${yesterday_iso}"
    if issue_already_exists_today "$CONFIG_COMPANIES_WHITESTAG_ID" "$issue_title"; then
      log "Skip — lessons issue with same title exists in last 24h."
      exit 0
    fi

    body=$(render_template "$HERE/templates/issue_lessons.md" \
      "YESTERDAY=${yesterday_iso}" \
      "TODAY=${today_iso}" \
      "RUN_LIST=${run_list}" \
      "VAULT_LESSONS_PATH_PATTERN=${CONFIG_VAULT_ROOT}/${CONFIG_VAULT_AGENTS_DIR}/<company-slug>/<agent-slug>/lessons/${today_iso}-<run-id-kurz>-<topic-slug>.md" \
      "VAULT_AGENT_PATH_PATTERN=${CONFIG_VAULT_ROOT}/${CONFIG_VAULT_AGENTS_DIR}/<company-slug>/<agent-slug>" \
      "MAX_RUNS=${CONFIG_LESSONS_MAX_RUNS}")

    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "DRY-RUN: would create lessons issue '$issue_title' assigned to vault-maintainer"
      echo "--- BODY ---"; echo "$body"; echo "--- END ---"
    else
      result=$(paperclip_create_issue "$CONFIG_COMPANIES_WHITESTAG_ID" \
        "$issue_title" "$body" "$CONFIG_VAULT_MAINTAINER_ID")
      issue_id=$(echo "$result" | jq -r '.id')
      log "Created lessons issue: $issue_id (${run_count} friction runs)"
      vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Reibungs-Sweep" \
        <<EOF
- ${run_count} friction runs handed to Vault-Maintainer (issue ${issue_id})
EOF
    fi
    log "Lessons-Loop done."
    ;;
```

- [ ] **Step 2: Dry-run smoke test**

Run:
```bash
CONFIG_FILE=scripts/agent-learning/templates/config.example.yaml \
  ./scripts/agent-learning/agent-learning-trigger.sh lessons --dry-run
```
Expected: Entweder `No friction runs ...` (wahrscheinlich, da keine echten Reibungs-Runs in den letzten 24h) oder eine `DRY-RUN: would create lessons issue ...` Zeile mit Body.

- [ ] **Step 3: Commit**

```bash
git add scripts/agent-learning/agent-learning-trigger.sh
git commit -m "feat(agent-learning): lessons mode (reibungs-sweep)"
```

---

## Task 13: Decay-Pass

**Files:**
- Create: `scripts/agent-learning/lib/decay.sh`
- Modify: `scripts/agent-learning/agent-learning-trigger.sh` (replace decay placeholder)
- Create: `scripts/agent-learning/tests/test_decay.sh`

- [ ] **Step 1: Write the failing test**

Create `scripts/agent-learning/tests/test_decay.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../lib/decay.sh"

SANDBOX=$(mktemp -d)
trap "rm -rf $SANDBOX" EXIT
mkdir -p "$SANDBOX/Skill-Wissen/n8n/_archive"

# Create a "stale" file (mtime 200 days ago) and a "fresh" one
echo "stale" > "$SANDBOX/Skill-Wissen/n8n/stale.md"
touch -t "$(date -v-200d +%Y%m%d0000 2>/dev/null || date -d '200 days ago' +%Y%m%d0000)" \
  "$SANDBOX/Skill-Wissen/n8n/stale.md"
echo "fresh" > "$SANDBOX/Skill-Wissen/n8n/fresh.md"

# Run decay with 180 days threshold
decay_archive_dir "$SANDBOX/Skill-Wissen/n8n" 180

[[ -f "$SANDBOX/Skill-Wissen/n8n/_archive/stale.md" ]] \
  || { echo "FAIL: stale.md not archived"; ls -la "$SANDBOX/Skill-Wissen/n8n/"; exit 1; }
[[ -f "$SANDBOX/Skill-Wissen/n8n/fresh.md" ]] \
  || { echo "FAIL: fresh.md disappeared"; exit 1; }
[[ ! -f "$SANDBOX/Skill-Wissen/n8n/stale.md" ]] \
  || { echo "FAIL: stale.md still in active dir"; exit 1; }

echo "OK: test_decay.sh"
```

```bash
chmod +x scripts/agent-learning/tests/test_decay.sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./scripts/agent-learning/tests/test_decay.sh`
Expected: FAIL — `decay.sh` doesn't exist.

- [ ] **Step 3: Implement decay.sh**

Create `scripts/agent-learning/lib/decay.sh`:
```bash
# Move files older than $2 days from $1 into $1/_archive/.
# Skips MEMORY.md, .gitkeep, dotfiles. Skips the _archive dir itself.

decay_archive_dir() {
  local dir="$1" days="$2"
  [[ -d "$dir" ]] || return 0
  mkdir -p "$dir/_archive"
  # find: -mtime +N → modified more than N days ago
  find "$dir" -maxdepth 1 -type f -name '*.md' -mtime "+${days}" \
    ! -name 'MEMORY.md' ! -name '.*' \
    -exec mv {} "$dir/_archive/" \;
}

decay_run() {
  # $1 = vault root, $2 = knowledge dir, $3 = agents dir,
  # $4 = knowledge_archive_after_days, $5 = lessons_archive_after_days
  local root="$1" k_dir="$2" a_dir="$3" k_days="$4" l_days="$5"

  # Knowledge: each domain
  if [[ -d "$root/$k_dir" ]]; then
    for d in "$root/$k_dir"/*/; do
      decay_archive_dir "$d" "$k_days"
    done
  fi

  # Lessons: each agent's lessons/ folder
  if [[ -d "$root/$a_dir" ]]; then
    for co_dir in "$root/$a_dir"/*/; do
      [[ -d "$co_dir" ]] || continue
      # skip _index.md, _status.md (these are files, not dirs — the loop already filters)
      for ag_dir in "$co_dir"*/; do
        [[ -d "${ag_dir}lessons" ]] && decay_archive_dir "${ag_dir}lessons" "$l_days"
      done
    done
  fi
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./scripts/agent-learning/tests/test_decay.sh`
Expected: `OK: test_decay.sh`

- [ ] **Step 5: Wire decay into the trigger**

In `scripts/agent-learning/agent-learning-trigger.sh`, add at the top of the source block:
```bash
source "$HERE/lib/decay.sh"
```

Replace the `decay)` placeholder with:
```bash
  decay)
    log "Decay-Pass starting"
    k_days=$(yq '.decay_pass.knowledge_archive_after_days' "$CONFIG_FILE")
    l_days=$(yq '.decay_pass.lessons_archive_after_days' "$CONFIG_FILE")

    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "DRY-RUN: would archive knowledge >${k_days}d and lessons >${l_days}d in $CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR"
    else
      decay_run "$CONFIG_VAULT_ROOT" "$CONFIG_VAULT_KNOWLEDGE_DIR" "$CONFIG_VAULT_AGENTS_DIR" "$k_days" "$l_days"
      vault_status_append "## $(date +"%Y-%m-%d %H:%M") — Decay-Pass" \
        <<EOF
- knowledge_archive_after_days: ${k_days}
- lessons_archive_after_days: ${l_days}
EOF
    fi
    log "Decay-Pass done."
    ;;
```

- [ ] **Step 6: Dry-run smoke test**

Run:
```bash
CONFIG_FILE=scripts/agent-learning/templates/config.example.yaml \
  ./scripts/agent-learning/agent-learning-trigger.sh decay --dry-run
```
Expected: `DRY-RUN: would archive knowledge >180d and lessons >90d ...`

- [ ] **Step 7: Commit**

```bash
git add scripts/agent-learning/lib/decay.sh scripts/agent-learning/agent-learning-trigger.sh scripts/agent-learning/tests/test_decay.sh
git commit -m "feat(agent-learning): decay pass"
```

---

## Task 14: launchd Plists

**Files:**
- Create: `scripts/agent-learning/launchd/de.whitestag.agent-learning.knowledge.plist`
- Create: `scripts/agent-learning/launchd/de.whitestag.agent-learning.lessons.plist`
- Create: `scripts/agent-learning/launchd/de.whitestag.agent-learning.decay.plist`

- [ ] **Step 1: Knowledge plist**

Create `scripts/agent-learning/launchd/de.whitestag.agent-learning.knowledge.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>de.whitestag.agent-learning.knowledge</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>$HOME/.paperclip/scripts/agent-learning-trigger.sh knowledge</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>1</integer>
    <key>Minute</key><integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/tmp/agent-learning-knowledge.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/agent-learning-knowledge.err.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 2: Lessons plist**

Create `scripts/agent-learning/launchd/de.whitestag.agent-learning.lessons.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>de.whitestag.agent-learning.lessons</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>$HOME/.paperclip/scripts/agent-learning-trigger.sh lessons</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>2</integer>
    <key>Minute</key><integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/tmp/agent-learning-lessons.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/agent-learning-lessons.err.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 3: Decay plist (Sundays 03:00)**

Create `scripts/agent-learning/launchd/de.whitestag.agent-learning.decay.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>de.whitestag.agent-learning.decay</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>$HOME/.paperclip/scripts/agent-learning-trigger.sh decay</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>0</integer>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/tmp/agent-learning-decay.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/agent-learning-decay.err.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 4: Validate XML**

Run:
```bash
for f in scripts/agent-learning/launchd/*.plist; do
  plutil -lint "$f" || { echo "FAIL: $f invalid"; exit 1; }
done
```
Expected: 3x `OK`.

- [ ] **Step 5: Commit**

```bash
git add scripts/agent-learning/launchd/
git commit -m "feat(agent-learning): launchd plists for 3 schedules"
```

---

## Task 15: install.sh / uninstall.sh

**Files:**
- Create: `scripts/agent-learning/install.sh`
- Create: `scripts/agent-learning/uninstall.sh`

- [ ] **Step 1: Implement install.sh**

Create `scripts/agent-learning/install.sh`:
```bash
#!/usr/bin/env bash
# Symlinks scripts to ~/.paperclip/scripts/, copies config template (if missing),
# installs launchd plists.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)

SCRIPTS_DST="$HOME/.paperclip/scripts"
CONFIG_DST="$HOME/.paperclip/instances/default/agent-learning.config.yaml"
LAUNCHD_DST="$HOME/Library/LaunchAgents"

echo "Installing agent-learning scripts to $SCRIPTS_DST"
mkdir -p "$SCRIPTS_DST/lib" "$SCRIPTS_DST/templates"

# Symlink top-level script
ln -sf "$HERE/agent-learning-trigger.sh" "$SCRIPTS_DST/agent-learning-trigger.sh"

# Symlink lib + templates as full dirs (replaces existing symlinks)
for src in "$HERE/lib"/*.sh; do
  ln -sf "$src" "$SCRIPTS_DST/lib/$(basename "$src")"
done
for src in "$HERE/templates"/*.md "$HERE/templates"/*.yaml; do
  [[ -e "$src" ]] && ln -sf "$src" "$SCRIPTS_DST/templates/$(basename "$src")"
done

# Config: copy only if not present (user file)
if [[ ! -f "$CONFIG_DST" ]]; then
  cp "$HERE/templates/config.example.yaml" "$CONFIG_DST"
  echo "Copied config template to $CONFIG_DST"
else
  echo "Config already exists at $CONFIG_DST — not overwriting."
fi

# Install launchd plists
echo "Installing launchd plists to $LAUNCHD_DST"
mkdir -p "$LAUNCHD_DST"
for plist in "$HERE/launchd"/*.plist; do
  label=$(basename "$plist" .plist)
  dst="$LAUNCHD_DST/$(basename "$plist")"

  # Substitute $HOME (launchd doesn't expand env vars in ProgramArguments string)
  sed "s|\$HOME|$HOME|g" "$plist" > "$dst"

  # Unload first if already loaded (safe to no-op)
  launchctl unload "$dst" 2>/dev/null || true
  launchctl load -w "$dst"
  echo "Loaded $label"
done

echo
echo "Install complete. Verify:"
echo "  launchctl list | grep agent-learning"
echo "  ./scripts/agent-learning/agent-learning-trigger.sh knowledge --dry-run"
```

```bash
chmod +x scripts/agent-learning/install.sh
```

- [ ] **Step 2: Implement uninstall.sh**

Create `scripts/agent-learning/uninstall.sh`:
```bash
#!/usr/bin/env bash
# Removes symlinks and unloads launchd plists.
# Config and vault content remain.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPTS_DST="$HOME/.paperclip/scripts"
LAUNCHD_DST="$HOME/Library/LaunchAgents"

echo "Unloading launchd plists"
for plist in "$LAUNCHD_DST"/de.whitestag.agent-learning.*.plist; do
  [[ -e "$plist" ]] || continue
  launchctl unload "$plist" 2>/dev/null || true
  rm -f "$plist"
  echo "Removed $(basename "$plist")"
done

echo "Removing script symlinks"
rm -f "$SCRIPTS_DST/agent-learning-trigger.sh"
for src in "$HERE/lib"/*.sh; do
  rm -f "$SCRIPTS_DST/lib/$(basename "$src")"
done
for src in "$HERE/templates"/*.md "$HERE/templates"/*.yaml; do
  [[ -e "$src" ]] && rm -f "$SCRIPTS_DST/templates/$(basename "$src")"
done

echo
echo "Uninstall complete. Config and vault contents kept."
echo "To also remove config: rm $HOME/.paperclip/instances/default/agent-learning.config.yaml"
```

```bash
chmod +x scripts/agent-learning/uninstall.sh
```

- [ ] **Step 3: Run install.sh**

Run: `./scripts/agent-learning/install.sh`
Expected: ohne Fehler. Verify:
```bash
launchctl list | grep agent-learning
ls -la ~/.paperclip/scripts/
ls -la ~/.paperclip/instances/default/agent-learning.config.yaml
```
Expected: 3 launchd-Einträge sichtbar, symlinks zeigen ins Repo, Config existiert.

- [ ] **Step 4: Commit**

```bash
git add scripts/agent-learning/install.sh scripts/agent-learning/uninstall.sh
git commit -m "feat(agent-learning): install / uninstall scripts"
```

---

## Task 16: Slug-Index initial generieren + Vault-Folder anlegen

**Files:**
- (Live writes into the vault)

- [ ] **Step 1: Generate slug index**

Run:
```bash
bash -c '
source ~/.paperclip/scripts/lib/config.sh
source ~/.paperclip/scripts/lib/paperclip_api.sh
source ~/.paperclip/scripts/lib/slug.sh
source ~/.paperclip/scripts/lib/vault_ops.sh

load_config
vault_check_mounted

WHITESTAG=$(paperclip_list_agents "$CONFIG_COMPANIES_WHITESTAG_ID")
HEALTH=$(paperclip_list_agents "$CONFIG_COMPANIES_HEALTH_ID")

mkdir -p "$CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR"
write_slug_index "$CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR/_index.md" \
  "whitestag" "$WHITESTAG" \
  "health" "$HEALTH"

echo "Wrote slug index to $CONFIG_VAULT_ROOT/$CONFIG_VAULT_AGENTS_DIR/_index.md"
'
```

Expected: Message + file existiert. Inhalt prüfen:
```bash
head -30 "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Agenten/_index.md"
```
Expected: Tabelle mit Slug, UUID, Company-Spalten, inkl. `online-recherche`, `vault-maintainer`.

- [ ] **Step 2: Ensure knowledge folders for all configured domains**

Run:
```bash
bash -c '
source ~/.paperclip/scripts/lib/config.sh
source ~/.paperclip/scripts/lib/vault_ops.sh
load_config

domains=$(yq ".domains | keys[]" "$CONFIG_FILE")
for d in $domains; do
  title=$(yq ".domains.${d}.title" "$CONFIG_FILE")
  vault_ensure_knowledge_domain "$d" "$title"
  echo "Ensured: $d"
done
'
```
Expected: eine Zeile pro Domain (`Ensured: n8n`, `Ensured: photoshop`, ...).

- [ ] **Step 3: Ensure agent folders for all whitestag + health agents**

Run:
```bash
bash -c '
source ~/.paperclip/scripts/lib/config.sh
source ~/.paperclip/scripts/lib/paperclip_api.sh
source ~/.paperclip/scripts/lib/slug.sh
source ~/.paperclip/scripts/lib/vault_ops.sh
load_config

TMPL="$HOME/.paperclip/scripts/templates/memory_initial.md"

for co_slug in whitestag health; do
  co_id_var="CONFIG_COMPANIES_$(echo $co_slug | tr a-z A-Z)_ID"
  co_id="${!co_id_var}"
  paperclip_list_agents "$co_id" | jq -r ".[] | [.name, .id] | @tsv" \
    | while IFS=$"\t" read -r name id; do
      slug=$(slug_from_name "$name")
      vault_ensure_agent "$co_slug" "$slug" "$name" "$TMPL"
      echo "Ensured: $co_slug/$slug"
    done
done
'
```
Expected: eine Zeile pro Agent.

- [ ] **Step 4: Verify in Obsidian**

Öffne Obsidian und navigiere zu `Paperclip/Agenten/whitestag/online-recherche/`. Erwartet: `MEMORY.md`, `lessons/`, `references/quellen.md`. Genauso für ein Health-Agent.

- [ ] **Step 5: Commit (kein Code-Change, aber Aktion als Marker)**

Diese Task schreibt nur in den Vault (externes State). Im Repo kein Commit nötig — Walter kann optional einen Tagesprotokoll-Eintrag machen.

---

## Task 17: AGENTS.md-Snippet zu allen whitestag + health Agenten ergänzen

**Files:**
- Modify: `~/.paperclip/instances/default/companies/<co>/agents/<ag>/instructions/AGENTS.md` (für alle whitestag + health Agenten)

- [ ] **Step 1: Append snippet to each AGENTS.md (idempotent — only if marker absent)**

Run:
```bash
bash -c '
source ~/.paperclip/scripts/lib/config.sh
source ~/.paperclip/scripts/lib/paperclip_api.sh
load_config

SNIPPET="$HOME/.paperclip/scripts/templates/agents_md_snippet.md"
MARKER="## Gedächtnis & Lernen"

for co_slug in whitestag health; do
  co_id_var="CONFIG_COMPANIES_$(echo $co_slug | tr a-z A-Z)_ID"
  co_id="${!co_id_var}"
  paperclip_list_agents "$co_id" | jq -r ".[] | .id" \
    | while read -r agent_id; do
      target="$HOME/.paperclip/instances/default/companies/$co_id/agents/$agent_id/instructions/AGENTS.md"
      if [[ -f "$target" ]]; then
        if grep -q "$MARKER" "$target"; then
          echo "Skip (already has snippet): $co_slug/$agent_id"
        else
          cat "$SNIPPET" >> "$target"
          echo "Appended: $co_slug/$agent_id"
        fi
      else
        echo "WARN: no AGENTS.md at $target"
      fi
    done
done
'
```

Expected: Mix von `Appended: ...` und `Skip (already has snippet): ...` Zeilen. Keine `WARN`.

- [ ] **Step 2: Verify one sample**

Run:
```bash
tail -25 "$HOME/.paperclip/instances/default/companies/9cebf3cf-efe8-4597-a400-f06488900a87/agents/d80fe6b9-b2ac-4d58-8525-8bbbb1d0caf7/instructions/AGENTS.md"
```
Expected: das Snippet aus `agents_md_snippet.md` (Header "Gedächtnis & Lernen", LESSON-CANDIDATE-Anweisung).

- [ ] **Step 3: Commit-Marker (kein Code-Change im Repo)**

Diese Edits gehen in User-State, nicht in den Repo. Kein git commit nötig.

---

## Task 18: End-to-End Smoke-Test (Knowledge-Loop, eine Domain forciert)

**Files:**
- (kein Code-Change, nur Verifikations-Run)

- [ ] **Step 1: Manuell ein Knowledge-Issue für n8n erzeugen**

Run:
```bash
~/.paperclip/scripts/agent-learning-trigger.sh knowledge --dry-run
```
Expected: Dry-Run zeigt das Issue, das *heute* erzeugt werden würde (je nach Wochentag).

Dann live:
```bash
# Temporärer Override für den Test: forciere eine spezifische Domain
# Wir nutzen die normale Wochentag-Logik — falls heute Sa/So → Override via env
CONFIG_FILE=$HOME/.paperclip/instances/default/agent-learning.config.yaml \
  ~/.paperclip/scripts/agent-learning-trigger.sh knowledge
```
Expected: `Created knowledge issue: <id> (...)` für die heutigen Domains. Falls kein Lauf erfolgt (Wochenende):
```bash
# Override für den Test
yq -i '.knowledge_loop.rotation.sat = ["n8n"]' \
  $HOME/.paperclip/instances/default/agent-learning.config.yaml
~/.paperclip/scripts/agent-learning-trigger.sh knowledge
# Nach dem Test rotation.sat wieder leeren
yq -i '.knowledge_loop.rotation.sat = []' \
  $HOME/.paperclip/instances/default/agent-learning.config.yaml
```

- [ ] **Step 2: Online-Recherche-Run beobachten**

Watch the server log:
```bash
tail -f ~/.paperclip/instances/default/logs/server.log | grep -i "recherche\|d80fe6b9"
```
Expected: Run startet binnen 1-2 Min (Online-Recherche hat `wakeOnDemand: true`, assignment sollte trigger sein), läuft 5-15 Min, beendet sich erfolgreich.

**Falls der Agent nicht aufwacht** (offene Spec-Frage zu wake-on-demand-vs-issue-assignment):
- Manueller Wake-Call: `curl -X POST http://127.0.0.1:3100/api/agents/d80fe6b9-b2ac-4d58-8525-8bbbb1d0caf7/wake`
- Falls das hilft → Trigger-Script in Task 11/12 erweitern um `paperclip_wake_agent` nach Issue-Create
- Falls auch das nicht hilft → diagnose: Server-Logs vergleichen mit erfolgreichen Runs

- [ ] **Step 3: Vault-Output prüfen**

Nach erfolgreichem Run:
```bash
ls -la "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Skill-Wissen/n8n/"
cat "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Skill-Wissen/n8n/MEMORY.md"
```
Expected: ein oder mehrere neue `2026-05-12-...md` Files (oder Issue auf `done` mit `no new actionable knowledge` Comment — beide Outcomes sind valide).

- [ ] **Step 4: Status-Log prüfen**

Run: `tail -20 "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Agenten/_status.md"`
Expected: Eintrag `## 2026-05-12 ... — Recherche-Pass (xxx)` mit Domains-Liste.

- [ ] **Step 5: Cleanup-Issue auflösen**

Das Test-Issue ist (a) auf `done` oder (b) `in_progress`. Wenn (b): warten oder manuell auf `done` schließen — kein Bug, sondern asynchroner Run.

- [ ] **Step 6: Commit Marker**

Kein Code-Change im Repo. Ergebnisse für Walter im nächsten Chatverlauf festhalten.

---

## Task 19: Documentation Snapshot in Vault `Anleitungen/`

**Files:**
- Create: `/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Anleitungen/Agent Nightly Learning.md`
- Modify: `/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Anleitungen/_index.md` (oder vergleichbarer Index, je nach Vault-Konvention)

Walter's Memory besagt: alle Anleitungen müssen als Snapshot im Vault liegen + Index-Eintrag. Diese Task erfüllt das für das frisch gebaute System.

- [ ] **Step 1: Snapshot der Anleitung im Vault erstellen**

Create `/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Anleitungen/Agent Nightly Learning.md`:
```markdown
# Agent Nightly Learning

> Snapshot — Stand 2026-05-12. Quelle: `docs/superpowers/{specs,plans}/2026-05-1{1,2}-agent-nightly-learning*.md` im Paperclip-Repo.

## Worum es geht

Paperclip-Agenten lernen jede Nacht dazu — zwei getrennte Schleifen:

1. **Knowledge-Loop (01:00):** Online-Recherche (Claude Sonnet 4.6) recherchiert pro Wochentag 1-2 Skill-Domänen (n8n, Photoshop, Blender, …) und schreibt Domain-Wissen nach `Paperclip/Skill-Wissen/<domain>/`.
2. **Lessons-Loop (02:00):** Vault-Maintainer (lokales LM Studio) sweept alle Reibungs-Runs der letzten 24h, destilliert Lessons pro Agent nach `Paperclip/Agenten/<company>/<agent>/lessons/` und syncht Context-Bundles zurück in die `instructions/`-Ordner der Agenten.

Sonntags 03:00 läuft zusätzlich ein **Decay-Pass**, der alte Files in `_archive/` verschiebt.

## Steuerung

Alles über eine Config: `~/.paperclip/instances/default/agent-learning.config.yaml`.

- **Rotation ändern:** `knowledge_loop.rotation.<weekday>` Liste anpassen.
- **Neue Domain hinzufügen:** Unter `domains:` Eintrag anlegen, dann in `rotation` aufnehmen.
- **Schedule verschieben:** `knowledge_loop.schedule` etc. anpassen UND launchd-Plists in `~/Library/LaunchAgents/de.whitestag.agent-learning.*.plist` updaten (Hour-Felder).
- **Decay-Threshold:** `decay_pass.knowledge_archive_after_days` / `decay_pass.lessons_archive_after_days`.

## Manuelle Trigger

```bash
# Sofort jetzt eine Domain-Recherche auslösen (überspringt Wochentag-Rotation):
~/.paperclip/scripts/agent-learning-trigger.sh knowledge

# Lessons-Sweep außerhalb von 02:00:
~/.paperclip/scripts/agent-learning-trigger.sh lessons

# Decay manuell:
~/.paperclip/scripts/agent-learning-trigger.sh decay

# Dry-Run (sieht, was passieren würde):
~/.paperclip/scripts/agent-learning-trigger.sh <mode> --dry-run
```

## Wo schaut man hin?

- **Wissen:** Vault → `Paperclip/Skill-Wissen/<domain>/`
- **Lessons:** Vault → `Paperclip/Agenten/<co>/<ag>/lessons/`
- **Lauf-Status:** Vault → `Paperclip/Agenten/_status.md`
- **Slug-Mapping:** Vault → `Paperclip/Agenten/_index.md`
- **launchd-Logs:** `/tmp/agent-learning-{knowledge,lessons,decay}.{out,err}.log`
- **Paperclip-Logs:** `~/.paperclip/instances/default/logs/server.log`

## Worauf achten

- Skills (`~/.claude/skills/<name>/SKILL.md`) werden **nie** automatisch verändert. Wenn Wissen aus dem Vault zu "Kern-Pattern" wird → manuelle Promotion durch Walter.
- Clara Sound ist ausgeschlossen — bekommt später eigenen Vault.
- Vault nicht gemounted → Trigger überspringt Schreiben (graceful degradation), `_status.md` zeigt Skip-Eintrag.

## Aufräumen

```bash
~/.paperclip/scripts/uninstall.sh  # ENTLÄDT launchd + Symlinks. Config/Vault bleiben.
```
```

- [ ] **Step 2: Index-Eintrag**

Check vault index convention:
```bash
ls "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Anleitungen/" | head -5
```

Wenn ein `_index.md` oder `README.md` o.ä. existiert: dort eine Zeile ergänzen `- [Agent Nightly Learning](Agent%20Nightly%20Learning.md) — automatisches nächtliches Lernen der Paperclip-Agenten`.

Falls kein Index-File: Walter darf manuell die Anleitung im Vault verlinken wo er möchte.

- [ ] **Step 3: Commit-Marker**

Kein Code-Change im Repo, der Snapshot ist im Vault.

---

## Task 20: Plan-Abschluss

**Files:**
- (kein Code-Change)

- [ ] **Step 1: Final-Verifikation**

Quick checklist:
```bash
# 1. All tests pass
for t in scripts/agent-learning/tests/*.sh; do "$t"; done

# 2. launchd jobs are loaded
launchctl list | grep agent-learning
# Expected: 3 entries

# 3. Vault structure exists
ls "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Skill-Wissen/"
ls "/Volumes/WHITESTAG-ARCHIV/Obsidian/WHITESTAG-Vault/Paperclip/Agenten/"

# 4. Vault-Maintainer is back on lmstudio_local
curl -s http://127.0.0.1:3100/api/agents/3067ea1d-5050-4032-aff5-1f759f544160 | jq '{adapterType, model: .adapterConfig.model}'

# 5. Config in place
ls -la ~/.paperclip/instances/default/agent-learning.config.yaml
```

- [ ] **Step 2: Final commit**

Wenn noch ungetrackte Marker-Files: einfach prüfen, dass alle Repo-Changes committed sind.

```bash
git status scripts/agent-learning/ docs/superpowers/
```
Expected: clean.

- [ ] **Step 3: Beobachten**

In den nächsten Tagen die Vault-Folder + `_status.md` durchschauen. Beim ersten Reibungs-Run im echten Betrieb prüfen, ob Vault-Maintainer die Lesson sauber destilliert. Wenn die Qualität auf LMStudio nicht reicht: Issue erzeugen → spätere Plan-Iteration evaluiert Modell-Upgrade oder Wechsel auf Hybrid mit lokalem Pre-Filter.
