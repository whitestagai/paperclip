# WHITESTAG-AI als Redundanz-Node — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der LM-Link-Node WHITESTAG-AI wird Fallback-Geraet fuer beide lokalen Modellfamilien, damit kein Agent mehr Primaermodell und Fallback auf derselben Maschine hat.

**Architecture:** Die Primaerlast bleibt unveraendert (25 gemma-Agenten am studio, 12 qwen-Agenten an der rtx). Am Node werden die beiden geladenen Modelle auf geraetesprechende IDs umbenannt, in beide Waechter-Dateien eingetragen und anschliessend als `fallbackModel` der betroffenen Agenten verdrahtet. Geaendert wird ausschliesslich das Feld `fallbackModel` — per `PATCH /agents/:id`, weil dieser Weg eine Revision in `agent_config_revisions` schreibt und damit den Rueckweg erhaelt.

**Tech Stack:** LM Studio CLI (`lms`) am Windows-PC, Python 3 (stdlib) fuer die Skripte, pytest fuer die Waechter-Tests, Paperclip REST-API auf `http://localhost:3100`, embedded Postgres auf Port 54329 (nur lesend).

**Spec:** `docs/superpowers/specs/2026-10-06-whitestag-ai-node-farm-einbindung-design.md`

## Global Constraints

- **Kontextfenster am Node: genau `98304`.** Untergrenze, nicht Zielwert. Unterhalb kuerzt der Adapter nicht (`BUDGET_LOOKUP_THRESHOLD_TOKENS = 32000`); der Versuch mit 65536 am 2026-08-25 trieb die Ueberlaeufe auf 67 % und die Erfolgsquote auf 0.
- **Slots am Node: `--parallel 2` je Modell.** 4+4 fordern 1,57 Mio Slot-Token aus ~6,5 GiB.
- **Neue Modell-IDs: `gemma-4-31b-win` und `qwen3.6-35b-win`.** Exakt diese Schreibweise, kleingeschrieben, in allen Dateien und Patches identisch.
- **qwen bleibt Q6_K** (`abiray/qwen3.6-35b-a3b`, 28,22 GiB). Die Q4_K_M-Variante wird NICHT geladen.
- **`gemma-4-31b-it@q8_0` am Node niemals laden** — 1,26 GB, ein Fragment.
- **Beim PATCH niemals `replaceAdapterConfig` setzen.** Ohne das Flag mergt der Server (`{ ...existingAdapterConfig, ...requestedAdapterConfig }`, `routes/agents.ts:2602`); mit ihm werden die uebrigen 12 Felder geloescht.
- **Den PII-Proxy nicht anfassen.** Dessen Geraetetrennung (`google/gemma-4-12b-qat` auf rtx, `google/gemma-4-12b` auf studio) ist bewusst gesetzt.
- **Primaerlast nicht verschieben.** Kein `model`-Feld wird dauerhaft geaendert; die einzige Ausnahme ist der Testagent in Task 5, dessen Wert im selben Task zurueckgeschrieben wird.

## Review Focus

- **Leeres oder falsch geschriebenes `fallbackModel`** — `endpoint-resolver.ts` loest `p.fallbackModel || p.primaryModel` auf. Ein Tippfehler fuehrt nicht zu einem Fehler, sondern zu einem stillen zweiten Versuch auf dem Primaermodell. Erwartung: jeder gesetzte Wert ist per `GET /api/v0/models/<id>` aufloesbar. Getestet in Task 4 und Task 6/7 (Nachkontrolle).
- **Node nicht erreichbar** — dann hat der Agent gar keinen Fallback mehr, wo er vorher auf das dauerhaft laufende 12B fiel. Erwartung: Erreichbarkeit vor jeder Welle geprueft. Getestet in Task 6, Schritt 1.
- **Node laedt mit abweichendem Fenster** — LM Studio kann beim Laden ein anderes Fenster setzen als angefordert. Ein Fallback mit zu kleinem Fenster kuerzt nicht und laeuft in `max_iterations`. Erwartung: geladenes Fenster ist >= 98304. Getestet in Task 2, Schritt 4.
- **`replaceAdapterConfig` versehentlich im Patch** — loescht die uebrigen 12 Felder der `adapter_config` bei 37 Agenten. Erwartung: Feldanzahl je Agent bleibt gleich. Getestet in Task 5, Schritt 5 und Task 6, Schritt 5.
- **Waechter-Datei vor dem Rename geaendert** — `modell-wacht` prueft gegen die `ps`-Identifier und meldet taeglich ein unbekanntes Modell, solange Soll und Ist auseinanderliegen. Erwartung: Aufsicht laeuft mit Exit 0. Getestet in Task 3, Schritt 4.

---

### Task 1: Rueckweg sichern

Vor jeder Aenderung wird der Ist-Stand der betroffenen Felder ausserhalb der Datenbank abgelegt. `agent_config_revisions` allein genuegt nicht: `rollbackConfigRevision` stellt die `afterConfig` einer Revision her, nicht die `beforeConfig` — ein Rollback auf die eigene Aenderung wuerde sie erneut anwenden.

**Files:**
- Create: `~/.paperclip/scripts/model-warden/fallback-ist-stand-20261006.json`
- Create: `/tmp/claude-scratch/export_fallback_ist.py` (Wegwerf-Skript)

**Interfaces:**
- Produces: JSON-Datei mit einer Liste von Objekten `{"id": str, "name": str, "model": str, "fallbackModel": str|None, "adapter_config_keys": int}` — Task 6 und 7 lesen sie zur Nachkontrolle.

- [ ] **Step 1: Export-Skript schreiben**

```python
#!/usr/bin/env python3
"""Ist-Stand der fallbackModel-Werte sichern. Wegwerf-Skript."""
import json, subprocess, os

SQL = """
SELECT json_agg(row_to_json(t)) FROM (
  SELECT a.id, a.name,
         a.adapter_config->>'model'         AS model,
         a.adapter_config->>'fallbackModel' AS "fallbackModel",
         (SELECT count(*) FROM jsonb_object_keys(a.adapter_config)) AS adapter_config_keys
  FROM agents a
  WHERE a.adapter_type = 'lmstudio_local'
    AND a.adapter_config->>'model' IN ('google/gemma-4-31b', 'qwen3.6-35b-a3b')
  ORDER BY a.adapter_config->>'model', a.name
) t;
"""

env = dict(os.environ, PGPASSWORD="paperclip")
out = subprocess.run(
    ["psql", "-h", "127.0.0.1", "-p", "54329", "-U", "paperclip",
     "-d", "paperclip", "-t", "-A", "-c", SQL],
    capture_output=True, text=True, env=env, check=True).stdout.strip()

rows = json.loads(out)
ziel = os.path.expanduser(
    "~/.paperclip/scripts/model-warden/fallback-ist-stand-20261006.json")
with open(ziel, "w") as fh:
    json.dump(rows, fh, indent=2, ensure_ascii=False)
print(f"{len(rows)} Agenten gesichert nach {ziel}")
```

- [ ] **Step 2: Skript ausfuehren**

Run: `/usr/bin/python3 /tmp/claude-scratch/export_fallback_ist.py`
Expected: `37 Agenten gesichert nach ...` — genau 37, denn 25 gemma- plus 12 qwen-Agenten.

- [ ] **Step 3: Datei pruefen**

```bash
/usr/bin/python3 -c "
import json, collections
d = json.load(open('$HOME/.paperclip/scripts/model-warden/fallback-ist-stand-20261006.json'))
print('Agenten:', len(d))
print(collections.Counter((r['model'], r['fallbackModel']) for r in d))
print('ohne id:', [r['name'] for r in d if not r['id']])
"
```

Expected: `Agenten: 37`, die Zaehlung zeigt `('google/gemma-4-31b', 'google/gemma-4-12b'): 25` und `('qwen3.6-35b-a3b', 'google/gemma-4-12b'): 12`, und `ohne id: []`.

- [ ] **Step 4: Commit**

Die Datei liegt unter `~/.paperclip/scripts/`, das unter `tools/` im Repo gespiegelt ist. Erst spiegeln, dann committen:

```bash
cd "/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip"
cp ~/.paperclip/scripts/model-warden/fallback-ist-stand-20261006.json tools/model-warden/
git add tools/model-warden/fallback-ist-stand-20261006.json
git commit -m "chore(model-warden): Ist-Stand der 37 fallbackModel-Werte vor der Node-Umstellung sichern"
```

---

### Task 2: Rename am Node (manuell am Windows-PC)

Dieser Task laeuft **nicht** vom Mac aus. `lms load` hat kein Geraete-Flag und wuerde auf das preferred device laden; ein globales Umschalten per `set-preferred-device` wuerde im Zeitfenster jeden anderen Ladevorgang auf den Node lenken, und der Entlade-Waerter laeuft alle 10 Minuten.

**Files:** keine im Repo — Zustandsaenderung am Node.

**Interfaces:**
- Produces: die Modell-IDs `gemma-4-31b-win` und `qwen3.6-35b-win`, am Node geladen mit Fenster 98304 und 2 Slots. Alle folgenden Tasks referenzieren genau diese Schreibweise.

- [ ] **Step 1: Ist-Zustand am Node festhalten**

Am Windows-PC:

```
lms ps
```

Expected: `gemma-4-31b-it` (18,69 GB) und `abiray/qwen3.6-35b-a3b` (30,30 GB), beide `IDLE`.

- [ ] **Step 2: gemma umbenennen**

```
lms unload gemma-4-31b-it
lms load gemma-4-31b-it@q4_k_m --identifier gemma-4-31b-win -c 98304 --parallel 2 -y
```

- [ ] **Step 3: qwen umbenennen**

```
lms unload abiray/qwen3.6-35b-a3b
lms load abiray/qwen3.6-35b-a3b --identifier qwen3.6-35b-win -c 98304 --parallel 2 -y
```

- [ ] **Step 4: Vom Mac aus gegenpruefen — Fenster und Geraet**

`/api/v0/models` ist unvollstaendig; die Einzelabfrage je ID ist die verlaessliche Probe (sie laedt das Modell nicht).

```bash
for id in gemma-4-31b-win qwen3.6-35b-win; do
  echo "--- $id"
  curl -s --max-time 10 "http://127.0.0.1:1234/api/v0/models/$id" \
   | /usr/bin/python3 -c "
import json,sys
d=json.load(sys.stdin)
ctx=d.get('loaded_context_length')
print('state      :', d.get('state'))
print('ctx geladen:', ctx, '-> OK' if ctx and ctx>=98304 else '-> ZU KLEIN, Task abbrechen')
"
done
~/.lmstudio/bin/lms link status
```

Expected: beide `state: loaded`, `ctx geladen: 98304` oder mehr, und `lms link status` listet unter `WHITESTAG-AI` genau `gemma-4-31b-win` und `qwen3.6-35b-win`. Erscheint dort noch ein alter Name, ist eine Instanz doppelt geladen — dann Step 2/3 fuer den verbliebenen Namen wiederholen.

- [ ] **Step 5: Keine alten IDs mehr aufloesbar**

```bash
for id in gemma-4-31b-it abiray/qwen3.6-35b-a3b; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
         "http://127.0.0.1:1234/api/v0/models/$id")
  echo "$id -> HTTP $code"
done
```

Expected: beide liefern **nicht** 200. Ein 200 bedeutet, dass die verbrannte ID weiterhin aufloest — dann ist der Rename unvollstaendig.

---

### Task 3: Resident-Set um das Geraet erweitern

`config.py` validiert `device` gegen die `devices`-Liste und wirft sonst `ValueError: Unbekanntes device`. Der Entlade-Waerter fasst den Node nicht an (`evict.py` filtert auf `device == "studio"` und ueberspringt Instanzen mit gesetztem `deviceIdentifier`); der Eintrag dokumentiert und schuetzt.

**Files:**
- Modify: `~/.paperclip/scripts/model-warden/resident-set.json`
- Modify: `~/.paperclip/scripts/model-warden/test_config.py` (Erwartung 9 -> 11 Eintraege)

**Interfaces:**
- Consumes: die Modell-IDs aus Task 2.
- Produces: Geraetename `whitestag-ai` in `devices` — Task 4 nutzt dieselbe Schreibweise nicht, aber kuenftige Eintraege richten sich danach.

- [ ] **Step 1: Test zuerst anpassen (er muss fehlschlagen)**

In `test_config.py`, Funktion `test_loads_real_set`: `assert len(entries) == 9` auf `11` setzen und die beiden Zusicherungen ergaenzen:

```python
def test_loads_real_set():
    entries = load_resident_set(os.path.join(HERE, "resident-set.json"))
    assert len(entries) == 11
    keys = {(e["load_key"], e["device"]) for e in entries}
    # coder-next lebt NUR auf der RTX (Tages-Boost). Der MacBook-Nacht-Fallback
    # wurde per Real-Test 2026-07-25 widerlegt (Guardrail p1 UND p4) -> coder-30b (Studio).
    assert ("qwen/qwen3-coder-next", "macbook") not in keys
    assert ("qwen/qwen3-coder-next", "rtx") in keys
    assert ("qwen/qwen3-coder-30b", "studio") in keys
    # Fallback-Klassifikator des PII-Proxys: MUSS auf der RTX liegen, also auf
    # einem anderen Geraet als das Primaermodell (studio). Faellt dieser Eintrag
    # weg, hat der Proxy im Stoerfall wieder keinen Fallback.
    assert ("google/gemma-4-12b-qat", "rtx") in keys
    assert ("google/gemma-4-12b", "studio") in keys
    # Fallback-Geraet beider Agentenfamilien seit 2026-10-06. Fallen diese
    # Eintraege weg, haben 25 gemma-Agenten ihren Fallback wieder auf
    # demselben Geraet wie das Primaermodell.
    assert ("gemma-4-31b-win", "whitestag-ai") in keys
    assert ("qwen3.6-35b-win", "whitestag-ai") in keys
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestaetigen**

Run: `cd ~/.paperclip/scripts/model-warden && /usr/bin/python3 -m pytest test_config.py -v`
Expected: FAIL in `test_loads_real_set` — `assert 9 == 11`. Die beiden anderen Tests bleiben gruen.

- [ ] **Step 3: Resident-Set erweitern**

In `resident-set.json` die `devices`-Liste auf
`["studio", "macbook", "rtx", "whitestag-ai"]` setzen und am Ende der
`models`-Liste die zwei Eintraege anfuegen:

```json
    {"device": "whitestag-ai", "ps_key": "gemma-4-31b-win", "load_key": "gemma-4-31b-it@q4_k_m", "ctx": 98304, "parallel": 2, "when": "always",
     "begruendung": "Fallback der 25 gemma-Agenten seit 06.10.2026. Vorher stand ihr Fallback auf google/gemma-4-12b — demselben Geraet wie ihr Primaermodell google/gemma-4-31b, der Fallback griff also bei einem Studio-Ausfall ins Leere. Geraet ist ein Windows-PC mit RTX 5090 (32 GB) + RTX 3090 (24 GB) = 56 GB VRAM. parallel 2 statt 4: bei 48,99 GB Gewichten beider Modelle bleiben nur ~6,5 GiB fuer zwei KV-Caches, und 4+4 forderten 1,57 Mio Slot-Token. ctx 98304 ist die belegte Untergrenze fuer Agentenmodelle. Q4_K_M gegen MLX 8-bit am studio ist ein Qualitaetsabstieg, aber der ersetzte Fallback war ein 12B."},

    {"device": "whitestag-ai", "ps_key": "qwen3.6-35b-win", "load_key": "abiray/qwen3.6-35b-a3b", "ctx": 98304, "parallel": 2, "when": "always",
     "begruendung": "Fallback der 12 qwen-Agenten inkl. C-Suite seit 06.10.2026, vorher google/gemma-4-12b (ein 12B als Fallback eines 35B). Bewusst Q6_K (28,22 GiB) und NICHT die kleinere Q4_K_M-Variante (lmstudio-community/qwen3.6-35b-a3b, 20,55 GiB), die ebenfalls am Node liegt: als Fallback ist Kapazitaet nicht der Engpass, Qualitaet geht vor. Primaermodell bleibt qwen3.6-35b-a3b in Q8_0 auf der rtx."}
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd ~/.paperclip/scripts/model-warden && /usr/bin/python3 -m pytest -v`
Expected: alle Tests PASS, insbesondere `test_loads_real_set` und `test_rejects_unknown_device`.

- [ ] **Step 5: Commit**

```bash
cd "/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip"
cp ~/.paperclip/scripts/model-warden/resident-set.json ~/.paperclip/scripts/model-warden/test_config.py tools/model-warden/
git add tools/model-warden/resident-set.json tools/model-warden/test_config.py
git commit -m "feat(model-warden): whitestag-ai als Fallback-Geraet ins Resident-Set"
```

---

### Task 4: soll-laufzeit.json erweitern und die Aufsicht gruen bekommen

`modell-wacht/pruefung.py` prueft die geladenen Modelle gegen die `ps`-Identifier und meldet unbekannte IDs. Steht die Datei vor dem Rename auf den neuen Namen, meldet sie taeglich einen Befund — darum laeuft dieser Task **nach** Task 2.

**Files:**
- Modify: `~/.paperclip/scripts/modell-wacht/soll-laufzeit.json`

**Interfaces:**
- Consumes: die Modell-IDs aus Task 2.

- [ ] **Step 1: Aufsicht im Ist-Zustand trocken laufen lassen**

`pruefung.py` hat **keinen** `__main__`-Block — ein direkter Aufruf tut
nichts und endet mit Exit 0. Einstiegspunkt ist `melder.py`, das bei
faelligen Befunden aber ein Paperclip-Issue anlegt und den Zustand
fortschreibt. Zum Verifizieren wird darum `pruefe()` direkt gerufen:

```bash
cd ~/.paperclip/scripts/modell-wacht && /usr/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from melder import pruefe
befunde, ergebnis = pruefe()
print('Kopfzeile:', ergebnis.get('kopfzeile'))
print('Befunde  :', len(befunde))
for b in befunde:
    print(' ', b.schwere, b.art, b.modell)
"
```

Expected: die Kopfzeile nennt `gegen 3 Sollwerte`, und unter den Befunden
kommt **kein** `gemma-4-31b-win` oder `qwen3.6-35b-win` vor. Die Aufsicht
prueft nur Modelle, die im Soll stehen; ein fehlender Soll-Eintrag erzeugt
keinen Befund. Erwartet sind die drei bekannten Befunde der Schwere
`niedrig` (ein nicht geladenes n8n-Modell, zwei Fenster groesser als
gefordert).

- [ ] **Step 2: Soll-Eintraege ergaenzen**

In `soll-laufzeit.json` zwei Schluessel auf oberster Ebene hinzufuegen:

```json
  "gemma-4-31b-win": {
    "contextLength": 98304,
    "parallel": 2,
    "begruendung": [
      "Fallback der 25 gemma-Agenten auf dem Node WHITESTAG-AI seit 06.10.2026.",
      "",
      "98304 ist dieselbe Untergrenze wie bei den Primaermodellen: unterhalb",
      "BUDGET_LOOKUP_THRESHOLD_TOKENS = 32000 kuerzt der Adapter nicht. Ein",
      "Fallback mit kleinerem Fenster laeuft in max_iterations statt zu helfen.",
      "",
      "parallel 2, nicht 4: der Node hat 56 GB VRAM (RTX 5090 + RTX 3090) und",
      "traegt zwei Modelle mit zusammen 48,99 GB Gewichten. 4+4 forderten",
      "1,57 Mio Slot-Token aus ~6,5 GiB — dieselbe Ueberbuchung, die auf der",
      "rtx am 26.08.2026 die Timeout-Welle ausloeste."
    ]
  },

  "qwen3.6-35b-win": {
    "contextLength": 98304,
    "parallel": 2,
    "begruendung": [
      "Fallback der 12 qwen-Agenten inkl. C-Suite auf dem Node seit 06.10.2026.",
      "",
      "Gleiche Untergrenze und gleiche Slot-Begruendung wie gemma-4-31b-win.",
      "",
      "Bewusst Q6_K und nicht die kleinere Q4_K_M-Variante, die am Node",
      "ebenfalls liegt: als Fallback ist Kapazitaet nicht der Engpass."
    ]
  }
```

- [ ] **Step 3: JSON-Syntax pruefen**

Run: `/usr/bin/python3 -c "import json; d=json.load(open('$HOME/.paperclip/scripts/modell-wacht/soll-laufzeit.json')); print(sorted(k for k in d if not k.startswith('_')))"`
Expected: `['gemma-4-31b-win', 'google/gemma-4-12b', 'google/gemma-4-31b', 'qwen3.6-35b-a3b', 'qwen3.6-35b-win']`

- [ ] **Step 4: Aufsicht muss die neuen Modelle ohne harten Befund pruefen**

```bash
cd ~/.paperclip/scripts/modell-wacht && /usr/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from melder import pruefe, signatur
befunde, ergebnis = pruefe()
print('Kopfzeile:', ergebnis.get('kopfzeile'))
for b in befunde:
    print(' ', b.schwere, b.art, b.modell)
print('harte Befunde:', len(signatur(befunde)))
"
```

Expected: die Kopfzeile nennt jetzt `gegen 5 Sollwerte` (vorher 3) — das
belegt, dass die neuen Eintraege gelesen werden. `harte Befunde: 0`.
Befunde der Schwere `niedrig` zu den neuen Modellen sind in Ordnung
(etwa `fenster_groesser`, wenn LM Studio ueber die Anforderung hinaus
laedt); jeder Befund hoeherer Schwere blockiert den naechsten Task.

- [ ] **Step 5: Commit**

```bash
cd "/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip"
cp ~/.paperclip/scripts/modell-wacht/soll-laufzeit.json tools/modell-wacht/
git add tools/modell-wacht/soll-laufzeit.json
git commit -m "feat(modell-wacht): Node-Fallback-Modelle ins Laufzeit-Soll"
```

---

### Task 5: Fallback an einem Agenten nachweisen

Ein unerprobter Fallback ist wertlos: dieser Codepfad schaltete am 2026-07-07 bei einem RAM-Guardrail-400 nicht um. Geprueft wird an **einem** unkritischen Agenten, und zwar so, dass kein anderer Agent betroffen ist. Das Primaermodell am studio wird **nicht** entladen — das traefe alle 25 gemma-Agenten gleichzeitig.

**Files:**
- Create: `/tmp/claude-scratch/fallback_probe.py` (Wegwerf-Skript)

**Interfaces:**
- Consumes: `fallback-ist-stand-20261006.json` aus Task 1.
- Produces: Nachweis, dass `usingFallback` greift. Ohne diesen Nachweis duerfen Task 6 und 7 nicht laufen.

- [ ] **Step 1: Testagenten waehlen und seinen Ist-Stand notieren**

Gewaehlt wird `Lektorat` — gemma-Fraktion, nicht zeitkritisch, nicht in der C-Suite.

```bash
export PGPASSWORD=paperclip
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT id, name, adapter_config->>'model', adapter_config->>'fallbackModel',
       (SELECT count(*) FROM jsonb_object_keys(adapter_config))
FROM agents WHERE name = 'Lektorat';"
```

Expected: eine Zeile mit `google/gemma-4-31b|google/gemma-4-12b` und einer Feldanzahl. Beide Werte und die Feldanzahl notieren — Step 5 vergleicht dagegen.

- [ ] **Step 2: Fallback auf den Node setzen und das Primaermodell gezielt brechen**

```python
#!/usr/bin/env python3
"""Fallback-Pfad an EINEM Agenten nachweisen. Wegwerf-Skript."""
import json, sys, urllib.request, os
sys.path.insert(0, os.path.expanduser("~/.paperclip/scripts"))
from paperclip_client import api_base, load_token

AGENT_ID = sys.argv[1]
PATCH = json.loads(sys.argv[2])

req = urllib.request.Request(
    f"{api_base()}/api/agents/{AGENT_ID}",
    data=json.dumps({"adapterConfig": PATCH}).encode(),
    headers={"Content-Type": "application/json",
             "Authorization": f"Bearer {load_token()}"},
    method="PATCH")
with urllib.request.urlopen(req, timeout=30) as r:
    out = json.loads(r.read())
cfg = out.get("adapterConfig") or out.get("adapter_config") or {}
print("model        :", cfg.get("model"))
print("fallbackModel:", cfg.get("fallbackModel"))
print("Feldanzahl   :", len(cfg))
```

Run, mit der ID aus Step 1:

```bash
/usr/bin/python3 /tmp/claude-scratch/fallback_probe.py <AGENT_ID> \
  '{"fallbackModel": "gemma-4-31b-win", "model": "gemma-4-31b-gibt-es-nicht"}'
```

Expected: `fallbackModel: gemma-4-31b-win`, `model: gemma-4-31b-gibt-es-nicht`, und die **Feldanzahl unveraendert gegenueber Step 1** — das belegt, dass der Server gemergt und nicht ersetzt hat.

- [ ] **Step 3: Einen Lauf ausloesen**

```bash
curl -s -X POST "http://localhost:3100/api/agents/<AGENT_ID>/heartbeat/invoke" \
  -H "Authorization: Bearer $(/usr/bin/python3 -c "
import sys,os; sys.path.insert(0, os.path.expanduser('~/.paperclip/scripts'))
from paperclip_client import load_token; print(load_token())")" \
  -H 'Content-Type: application/json' -d '{}' | head -c 400
```

Expected: eine Run-ID oder eine Bestaetigung, dass der Lauf angestossen wurde.

- [ ] **Step 4: Nachweisen, dass der Fallback griff**

Der direkte Nachweis steht in `cost_events`: dort wird das tatsaechlich
benutzte Modell je Lauf gebucht.

```bash
export PGPASSWORD=paperclip
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT model, count(*) AS buchungen, max(occurred_at) AS zuletzt
FROM cost_events
WHERE agent_id = '<AGENT_ID>' AND occurred_at > now() - interval '20 minutes'
GROUP BY 1 ORDER BY 2 DESC;"
```

Expected: eine Zeile mit `model = gemma-4-31b-win`. Erscheint stattdessen nur
`gemma-4-31b-gibt-es-nicht` oder gar nichts, hat der Fallback **nicht**
gegriffen.

Ergaenzend der Lauf-Status und die Ereignisse (die Tabelle heisst
`heartbeat_runs`, nicht `runs`; die Volltext-Logs liegen ausserhalb der DB
unter `log_store`/`log_ref`):

```bash
export PGPASSWORD=paperclip
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT id, status, error, log_store, log_ref
FROM heartbeat_runs WHERE agent_id = '<AGENT_ID>'
ORDER BY created_at DESC LIMIT 1;"
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT seq, event_type, level, left(message, 160)
FROM heartbeat_run_events
WHERE run_id = (SELECT id FROM heartbeat_runs WHERE agent_id = '<AGENT_ID>'
                ORDER BY created_at DESC LIMIT 1)
ORDER BY seq;"
```

Expected: ein Lauf mit `status = succeeded`, der nicht an einem Modellfehler
scheitert.

**Bleibt der Nachweis in `cost_events` aus, endet die Umsetzung hier** — dann
schaltet der Fallback-Pfad nicht um, und Task 6/7 wuerden 37 Agenten auf
einen Fallback stellen, der nicht greift.

- [ ] **Step 5: Beide Felder zurueckschreiben und vergleichen**

```bash
/usr/bin/python3 /tmp/claude-scratch/fallback_probe.py <AGENT_ID> \
  '{"fallbackModel": "google/gemma-4-12b", "model": "google/gemma-4-31b"}'
```

Expected: genau die Werte und die Feldanzahl aus Step 1. Abweichung bedeutet Feldverlust — dann den Agenten aus `fallback-ist-stand-20261006.json` wiederherstellen.

- [ ] **Step 6: Revision pruefen**

```bash
curl -s "http://localhost:3100/api/agents/<AGENT_ID>/config-revisions" \
  -H "Authorization: Bearer $(/usr/bin/python3 -c "
import sys,os; sys.path.insert(0, os.path.expanduser('~/.paperclip/scripts'))
from paperclip_client import load_token; print(load_token())")" \
 | /usr/bin/python3 -c "
import json,sys
for r in json.load(sys.stdin)[:3]:
    print(r.get('source'), r.get('changedKeys'))
"
```

Expected: mindestens zwei Revisionen mit `source: patch` und `changedKeys`, die `adapterConfig` nennen — der Rueckweg ist dokumentiert.

---

### Task 6: Welle A — die 25 gemma-Agenten

**Files:**
- Create: `/tmp/claude-scratch/umstellen_welle.py` (Wegwerf-Skript, auch Task 7 nutzt es)

**Interfaces:**
- Consumes: `fallback-ist-stand-20261006.json` aus Task 1; den Nachweis aus Task 5.
- Produces: 25 Agenten mit `fallbackModel = gemma-4-31b-win`.

- [ ] **Step 1: Erreichbarkeit des Node pruefen**

```bash
~/.lmstudio/bin/lms link status | grep -A4 WHITESTAG-AI
curl -s -o /dev/null -w 'gemma-4-31b-win -> HTTP %{http_code}\n' --max-time 10 \
  "http://127.0.0.1:1234/api/v0/models/gemma-4-31b-win"
```

Expected: `Status: connected` und `HTTP 200`. Ist der Node nicht erreichbar, wird nicht umgestellt — der heutige Fallback auf das dauerhaft laufende 12B waere dann besser.

- [ ] **Step 2: Umstell-Skript schreiben**

```python
#!/usr/bin/env python3
"""fallbackModel einer Agentengruppe umstellen. Wegwerf-Skript.

Aufruf: umstellen_welle.py <primaermodell> <neuer_fallback> [--trocken]
"""
import json, os, subprocess, sys, urllib.request
sys.path.insert(0, os.path.expanduser("~/.paperclip/scripts"))
from paperclip_client import api_base, load_token

PRIMAER, NEU = sys.argv[1], sys.argv[2]
TROCKEN = "--trocken" in sys.argv

env = dict(os.environ, PGPASSWORD="paperclip")
rows = subprocess.run(
    ["psql", "-h", "127.0.0.1", "-p", "54329", "-U", "paperclip", "-d", "paperclip",
     "-t", "-A", "-F", "|", "-c",
     "SELECT id, name, (SELECT count(*) FROM jsonb_object_keys(adapter_config)) "
     "FROM agents WHERE adapter_type='lmstudio_local' "
     f"AND adapter_config->>'model' = '{PRIMAER}' ORDER BY name"],
    capture_output=True, text=True, env=env, check=True).stdout.strip().splitlines()

print(f"{len(rows)} Agenten mit model={PRIMAER} -> fallbackModel={NEU}")
if TROCKEN:
    for r in rows:
        print("  wuerde umstellen:", r.split("|")[1])
    sys.exit(0)

token = load_token()
fehler = []
for r in rows:
    aid, name, felder_vorher = r.split("|")
    req = urllib.request.Request(
        f"{api_base()}/api/agents/{aid}",
        data=json.dumps({"adapterConfig": {"fallbackModel": NEU}}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            cfg = (json.loads(resp.read()).get("adapterConfig") or {})
        ok = cfg.get("fallbackModel") == NEU and len(cfg) == int(felder_vorher)
        print(f"  {'OK  ' if ok else 'FEHL'} {name}  Felder {felder_vorher} -> {len(cfg)}")
        if not ok:
            fehler.append(name)
    except Exception as e:
        print(f"  FEHL {name}: {e}")
        fehler.append(name)

print(f"\nfehlerhaft: {len(fehler)}", fehler or "")
sys.exit(1 if fehler else 0)
```

- [ ] **Step 3: Trockenlauf**

Run: `/usr/bin/python3 /tmp/claude-scratch/umstellen_welle.py google/gemma-4-31b gemma-4-31b-win --trocken`
Expected: `25 Agenten mit model=google/gemma-4-31b -> fallbackModel=gemma-4-31b-win` und 25 Namen. Eine andere Zahl als 25 bedeutet, dass sich der Bestand seit Task 1 geaendert hat — dann Task 1 wiederholen.

- [ ] **Step 4: Umstellen**

Run: `/usr/bin/python3 /tmp/claude-scratch/umstellen_welle.py google/gemma-4-31b gemma-4-31b-win`
Expected: 25 Zeilen mit `OK`, gleiche Feldanzahl vor und nach dem Patch, `fehlerhaft: 0`, Exit 0.

- [ ] **Step 5: Nachkontrolle gegen den Ist-Stand**

```bash
export PGPASSWORD=paperclip
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT adapter_config->>'model', adapter_config->>'fallbackModel', count(*)
FROM agents WHERE adapter_type='lmstudio_local' GROUP BY 1,2 ORDER BY 3 DESC;"
/usr/bin/python3 -c "
import json, subprocess, os
ist = json.load(open(os.path.expanduser('~/.paperclip/scripts/model-warden/fallback-ist-stand-20261006.json')))
env = dict(os.environ, PGPASSWORD='paperclip')
jetzt = dict(l.split('|') for l in subprocess.run(
    ['psql','-h','127.0.0.1','-p','54329','-U','paperclip','-d','paperclip','-t','-A','-F','|','-c',
     \"SELECT id, (SELECT count(*) FROM jsonb_object_keys(adapter_config))::text FROM agents WHERE adapter_type='lmstudio_local'\"],
    capture_output=True, text=True, env=env, check=True).stdout.strip().splitlines())
verloren = [r['name'] for r in ist if r['id'] in jetzt and int(jetzt[r['id']]) != r['adapter_config_keys']]
print('Agenten mit veraenderter Feldanzahl:', verloren or 'keine')
"
```

Expected: `google/gemma-4-31b|gemma-4-31b-win|25`, die 12 qwen-Agenten noch auf `google/gemma-4-12b`, und `Agenten mit veraenderter Feldanzahl: keine`.

- [ ] **Step 6: 24 Stunden beobachten**

```bash
export PGPASSWORD=paperclip
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT date_trunc('day', created_at)::date AS tag, count(*)
FROM heartbeat_runs WHERE status = 'failed'
  AND created_at > now() - interval '8 days'
GROUP BY 1 ORDER BY 1;"
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT model, count(*) FROM cost_events
WHERE created_at > now() - interval '1 day' GROUP BY 1 ORDER BY 2 DESC;"
```

Expected: die Zahl fehlgeschlagener Laeufe am Umstelltag nicht hoeher als an den Vortagen, und bei `cost_events` **keine** nennenswerte Last auf `gemma-4-31b-win`. Einzelne Aufrufe dort sind der erwartete Fall eines greifenden Fallbacks; ein dauerhafter Anteil waere ein Hinweis, dass Primaerlast abgewandert ist.

---

### Task 7: Welle B — die 12 qwen-Agenten

Erst nach erfolgreichem Task 6, Step 6. Diese Gruppe enthaelt die C-Suite (CEO, CTO, CPO, CRO, CHO).

**Files:** keine neuen — nutzt das Skript aus Task 6.

**Interfaces:**
- Consumes: das Skript aus Task 6; die Beobachtung aus Task 6, Step 6.
- Produces: 12 Agenten mit `fallbackModel = qwen3.6-35b-win`.

- [ ] **Step 1: Erreichbarkeit des qwen-Modells pruefen**

```bash
curl -s -o /dev/null -w 'qwen3.6-35b-win -> HTTP %{http_code}\n' --max-time 10 \
  "http://127.0.0.1:1234/api/v0/models/qwen3.6-35b-win"
```

Expected: `HTTP 200`.

- [ ] **Step 2: Trockenlauf**

Run: `/usr/bin/python3 /tmp/claude-scratch/umstellen_welle.py qwen3.6-35b-a3b qwen3.6-35b-win --trocken`
Expected: `12 Agenten` und die Namen Blender, Bueroleitung, CEO, CHO, CPO, CRO, CTO, Online-Rechercheur, Recherche, SEO/GEO-Spezialist, Sekretaerin, Trainingscoach.

- [ ] **Step 3: Umstellen**

Run: `/usr/bin/python3 /tmp/claude-scratch/umstellen_welle.py qwen3.6-35b-a3b qwen3.6-35b-win`
Expected: 12 Zeilen `OK`, `fehlerhaft: 0`, Exit 0.

- [ ] **Step 4: Abnahme — kein Agent mit Fallback auf demselben Geraet**

```bash
export PGPASSWORD=paperclip
psql -h 127.0.0.1 -p 54329 -U paperclip -d paperclip -t -A -F'|' -c "
SELECT adapter_config->>'model' AS primaer,
       adapter_config->>'fallbackModel' AS fallback, count(*)
FROM agents WHERE adapter_type='lmstudio_local'
GROUP BY 1,2 ORDER BY 3 DESC;"
```

Expected genau:
`google/gemma-4-31b|gemma-4-31b-win|25`,
`qwen3.6-35b-a3b|qwen3.6-35b-win|12`,
und die zwei Agenten ohne Fallback (openbiollm, gemma-4-12b) unveraendert. Kein Paar, bei dem Primaer und Fallback auf demselben Geraet liegen — zu pruefen gegen `resident-set.json`: `google/gemma-4-31b` ist `studio`, `gemma-4-31b-win` ist `whitestag-ai`; `qwen3.6-35b-a3b` ist `rtx`, `qwen3.6-35b-win` ist `whitestag-ai`.

- [ ] **Step 5: Aufsicht und Waechter-Tests ein letztes Mal**

```bash
cd ~/.paperclip/scripts/modell-wacht && /usr/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from melder import pruefe, signatur
b, e = pruefe()
print(e.get('kopfzeile')); print('harte Befunde:', len(signatur(b)))
"
cd ~/.paperclip/scripts/model-warden && /usr/bin/python3 -m pytest -q; echo "tests exit=$?"
```

Expected: `harte Befunde: 0` und `tests exit=0`.

- [ ] **Step 6: Deploy-Luecke schliessen und committen**

`~/.paperclip/scripts/` ist unter `tools/` gespiegelt; `diff -rq` ist der Drift-Test.

```bash
cd "/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip"
diff -rq ~/.paperclip/scripts/model-warden tools/model-warden | grep -v __pycache__ || echo "model-warden deckungsgleich"
diff -rq ~/.paperclip/scripts/modell-wacht tools/modell-wacht | grep -v __pycache__ || echo "modell-wacht deckungsgleich"
git status --short tools/
git add tools/model-warden tools/modell-wacht
git commit -m "feat(farm): WHITESTAG-AI ist Fallback-Geraet beider Agentenfamilien"
```

Expected: beide Verzeichnisse deckungsgleich, Commit sauber.
