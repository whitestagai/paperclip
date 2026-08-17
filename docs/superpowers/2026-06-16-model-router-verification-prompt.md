# Per-Task-Modell-Router verifizieren (deployed 2026-06-14, Test am 2026-06-16)

> Selbst-enthaltender Prüf-Prompt. Eine frische Session (auch ein anderes Modell)
> kann damit ohne Vorwissen den Router testen. Auf Deutsch antworten.

Arbeitsverzeichnis:
`/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip`

## Was getestet wird
Am 2026-06-14 wurde ein "Per-Task-Modell-Router" für die lokalen LM-Studio-Agenten
(Paperclip) live geschaltet. Pro Aufgabe entscheidet er, ob ein Qwen-Default-Agent
das Reasoning-Modell (`qwen3.6-35b-a3b-turboquant-mlx`) behält ODER eine sicher-triviale
Aufgabe auf das schnelle "cheap"-Profil (`gemma-4-31b-it-mlx`) heruntergeroutet wird.
- Hybrid: Phase-1-Regeln + Phase-2-Mini-Klassifikator (warmes Gemma, fail-safe auf Reasoning).
- Eingehängt im Heartbeat-Dispatch; nutzt die bestehende modelProfile-Maschinerie,
  Quelle = `"auto_router"`.
- Opt-in via Env `PAPERCLIP_MODEL_ROUTER=on` (gesetzt in
  `~/.paperclip/scripts/launchd-paperclip.sh`; Server-Job: launchd `ing.paperclip.dev`, :3100).
- 24 Qwen-Default-lmstudio-Agenten über 3 Companies wurden mit `cheap=Gemma` geseedet.
- Default ist IMMER Qwen — jeder Fehler/Zweifel fällt sicher dorthin zurück.

## Wichtig fürs Verständnis der Metadaten (sonst Fehlinterpretation!)
Router-Metadaten landen in `heartbeat_runs.result_json->'modelProfile'`
(`requestedBy`, `applied`, `routerReason`). ABER: Metadaten werden NUR geschrieben,
wenn tatsächlich auf cheap heruntergeroutet wurde. Hält der Router Qwen (substanzieller
Task / hohe Prio / Fehlerhistorie / Klassifikator sagt "reasoning"), ist `profile=null`
→ KEINE modelProfile-Metadaten. Heißt:
- `requestedBy='auto_router'` erscheint AUSSCHLIESSLICH bei Gemma-Downgrades.
- sichtbare `routerReason` ∈ {`short_non_substantive` (Regel), `classifier_fast` (Klassifikator)}.
- Die "Qwen behalten"-Fälle sieht man NICHT in den Metadaten (nur in Server-Logs).
  Erwarte also keine `applied='default'`-Zeilen.

## DB-Zugang
`psql "postgres://paperclip:paperclip@localhost:54329/paperclip"`

## Schritt 1 — Ist der Router überhaupt noch aktiv?
- `grep PAPERCLIP_MODEL_ROUTER ~/.paperclip/scripts/launchd-paperclip.sh` → muss `="on"` zeigen.
- `launchctl print "gui/$(id -u)/ing.paperclip.dev" | grep -i "state ="` → running.
- `curl -sf http://127.0.0.1:3100/api/health` → 200.
Wenn eins fehlt: Router ist (teils) aus → in Befund vermerken, NICHT raten.

## Schritt 2 — Hat der Router in den letzten 2 Tagen gefeuert? (Kernfrage)
```
psql "postgres://paperclip:paperclip@localhost:54329/paperclip" -P pager=off -c "
SELECT a.name,
       hr.result_json->'modelProfile'->>'routerReason' AS reason,
       count(*) AS n,
       count(*) FILTER (WHERE hr.status='succeeded') AS ok,
       count(*) FILTER (WHERE hr.status='failed')    AS failed
FROM heartbeat_runs hr JOIN agents a ON a.id=hr.agent_id
WHERE hr.created_at > now() - interval '2 days'
  AND hr.result_json->'modelProfile'->>'requestedBy'='auto_router'
GROUP BY 1,2 ORDER BY n DESC;"
```
→ Erwartung: ≥1 Zeile mit applied=cheap. Aufschlüsselung Regel (`short_non_substantive`)
  vs Klassifikator (`classifier_fast`).

## Schritt 3 — Sicherheits-/Regressions-Check
a) Fehlerrate der cheap-Runs: drehen heruntergeroutete Tasks häufiger durch?
```
psql "postgres://paperclip:paperclip@localhost:54329/paperclip" -P pager=off -c "
SELECT
  count(*) FILTER (WHERE rj->>'requestedBy'='auto_router') AS cheap_runs,
  count(*) FILTER (WHERE rj->>'requestedBy'='auto_router' AND hr.status='failed') AS cheap_failed,
  count(*) FILTER (WHERE rj->>'requestedBy'='auto_router' AND hr.error_code IN ('max_iterations','timeout')) AS cheap_spun
FROM heartbeat_runs hr, LATERAL (SELECT hr.result_json->'modelProfile' AS rj) x
WHERE hr.created_at > now() - interval '2 days';"
```
→ Wenn cheap_spun/cheap_failed auffällig hoch: Schwelle (600 Zeichen) zu aggressiv → melden.
b) Anti-Loop: kein Issue mit Fehlerhistorie sollte cheap-geroutet sein (stichprobenartig prüfen).

## Schritt 4 — Modelle noch resident? (sonst Ladezeit statt 0-Latenz)
`lms ps` → `qwen3.6-35b-a3b-turboquant-mlx` UND `gemma-4-31b-it-mlx` beide geladen?

## Wenn NICHTS gefeuert hat (0 auto_router-Runs)
Diagnose der Reihe nach:
1. Liefen überhaupt Qwen-Default-Dispatches?  `count(*) heartbeat_runs` letzte 2 Tage.
2. Seed noch da?
   ```
   SELECT count(*) FROM agents WHERE adapter_type='lmstudio_local'
     AND adapter_config->'modelProfiles'->'cheap'->'adapterConfig'->>'model'='gemma-4-31b-it-mlx';
   ```
   (erwartet 24)
3. Env wirklich im laufenden Prozess? Wrapper-Restart nach dem Setzen passiert?
4. Vielleicht waren alle Tasks substanziell/lang → Regeln hielten korrekt Qwen
   (dann ist "0 cheap" KEIN Bug, sondern konservatives Verhalten). In dem Fall lohnt
   ein Blick in die Server-Logs auf `routerReason='inconclusive'` (Klassifikator-Konsultationen).

## Relevante Dateien (Code)
- `server/src/services/model-router.ts`            (Regeln)
- `server/src/services/model-router-signals.ts`    (Kill-Switch + Anti-Loop-Query)
- `server/src/services/model-router-classifier.ts` (Phase-2-Klassifikator)
- `server/src/services/heartbeat.ts`               (Wiring, suche `routerApplies`)
- `scripts/seed-cheap-model-profile.mjs`           (Seed)
- `docs/superpowers/specs|plans/2026-06-14-per-task-model-router*`  (Spec + Plan)
- Backup der Pre-Seed-Configs: `/tmp/lmstudio-adapter-config-backup-2026-06-14.json` (ggf. weg nach Reboot)

## Liefere am Ende
1. Läuft der Router? (ja/nein, mit Beleg)
2. cheap/Regel-vs-Klassifikator-Verteilung der letzten 2 Tage.
3. Gibt es Regressions-Signale (höhere Fehler-/Spin-Rate bei cheap)?
4. Empfehlung: Schwellwerte so lassen / nachschärfen / Router pausieren — oder Phase 3
   (Self-Escalation) angehen. Knapp begründet.

Kill-Switch zum Pausieren: `PAPERCLIP_MODEL_ROUTER="off"` im Wrapper + `launchctl kickstart -k "gui/$(id -u)/ing.paperclip.dev"`.
