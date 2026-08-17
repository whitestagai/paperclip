# PII-Proxy Classifier — Modellwahl & DE-Benchmark

- **Datum:** 2026-06-14
- **Hardware:** Apple M4 Max, 128 GB RAM (RAM ist KEINE Einschränkung)
- **Methode:** (1) Deep-Research (20 Quellen, 25 Claims adversarial verifiziert), (2) eigenes
  deutsches PII/Art.9-Benchmark gegen den **echten** DPO-Classifier-Prompt
  (`opensource/pii-proxy/bench/de-pii-bench/`, Wegwerf-Instanz auf :4712, Live-:4711 unberührt).

---

> **UPDATE 2026-06-14: Leak BEHOBEN.** Regex-Detektoren `creditcard.ts` (Luhn) + `apikey.ts`
> ergänzt **und** in der Rules-Allowlist (`detect.pii`) freigeschaltet (Commits `9554339` + `59672f0`
> auf `feat/openai-chat-completions-passthrough`). Live auf :4711 verifiziert: Visa/Mastercard →
> `[KREDITKARTE_A]`, OpenAI/AWS/GitHub-Keys → `[API_KEY_*]`; kein Regress (PERSON/IBAN/Art.9 intakt).
> Gotcha: ein Detektor muss zusätzlich zur Registrierung in `pii-proxy-rules.default.yaml`
> `detect.pii` stehen, sonst läuft er zur Laufzeit nie (Guard-Test ergänzt).

## 🔴 Ursprünglicher Befund (jetzt behoben): Kreditkarten & API-Keys leakten — modell-UNABHÄNGIG

Das Benchmark zeigt am IST-Modell (gemma-4-31b):

| Kategorie | Recall | Status |
|---|---|---|
| KREDITKARTE (4111…, 5555…) | **0/2 (0 %)** | 🔴 durchgerutscht |
| API_KEY (`sk-proj-…`, `ghp_…`, `AKIA…`) | **0/3 (0 %)** | 🔴 durchgerutscht |

**Ursache (keine Modellfrage):** Der Proxy hat **Regex-Detektoren** nur für
IBAN, BIC, EMAIL, PHONE, PLZ, Steuernummer, USt-ID, URL — **nicht** für Kreditkarten oder
API-Keys/Secrets. Der LLM-Classifier-Prompt fragt diese Kategorien ebenfalls nicht ab. Folglich
fängt sie **kein** Modell, auch kein größeres. **Das ist ein echtes Leck im Produktivbetrieb.**

**Fix (eigener Task, modell-unabhängig):**
1. **Regex-Detektoren ergänzen** in `pii-proxy/packages/core/src/detectors/`:
   - `creditcard.ts`: 13–19-stellige Kartennummern **mit Luhn-Prüfung** (vermeidet Fehlalarme).
   - `apikey.ts`: bekannte Secret-Präfixe (`sk-`, `sk-proj-`, `ghp_`/`gho_`/`ghs_`, `AKIA`/`ASIA`,
     `xoxb-`, `AIza`, generische `[A-Za-z0-9_\-]{32,}` hinter Schlüssel-Keywords).
   Regex ist hier **zuverlässiger als ein LLM** (strukturierte Tokens, deterministisch).
2. Optional zusätzlich den Classifier-Prompt um `KREDITKARTE`/`SECRET` erweitern (Fallback für
   unstrukturierte Fälle). Regex bleibt die primäre Absicherung.

---

## Baseline gemma-4-31b-it (IST-Produktion) — Genauigkeitsprofil

| Metrik | Wert |
|---|---|
| Art.9-Block | **5/5 (100 %)** ✓ |
| PERSON / FIRMA | 4/4 / 4/4 (100 %) ✓ |
| EMAIL / PHONE / IBAN / BIC / Steuernr. | 100 % (Regex+LLM) ✓ |
| ORT | 3/4 (75 %) — verfehlt „Bahnhofstraße 5" (Straße ohne PLZ) |
| Negative (Falsch-Block) | 0/3 ✓ (1 harmlose Über-Ersetzung) |
| Latenz/Call (kleine Prompts) | p50 **5,6 s**, mean 5,1 s, max 10,7 s |

Die ~5 s **pro Call** sind der Compute-Floor des 31B — bei großen Agent-Prompts (prefill-lastig)
explodiert das, weshalb Chunking nötig war. **Genau das ist der Hebel für ein kleineres Modell.**

---

## Deep-Research-Erkenntnisse (verifiziert)

- **Reasoning-Modelle sind schlechter** für strikte JSON-Klassifikation: CoT senkt die
  Instruktions-Befolgung messbar (3-0). [arXiv 2505.11423](https://arxiv.org/pdf/2505.11423) →
  Verwerfung von qwen3.6-a3b war korrekt.
- **Dedizierte PII/NER-Modelle (Piiranha, GLiNER-PII, GLiNER2-PII) scheiden aus** (je 3-0): kein
  Art.9, oft keine ORG, **keine gemessene deutsche** NER-Genauigkeit, **nicht MLX/LM-Studio**
  (Encoder → separate Python/ONNX-Pipeline). Ein dediziertes NER-Modell **schlägt das LLM NICHT**
  für volle GDPR-Abdeckung.
- **gemma-3-27b-it als MLX-QAT-4bit verfügbar** (~14 GB, 3-0) — echter Drop-in für die JSON-Prompt-
  Pipeline. [mlx-community](https://huggingface.co/mlx-community/gemma-3-27b-it-qat-4bit)
- **MLX ist decode-schnell, aber prefill-langsam** vs. llama.cpp (3-0) — der Classifier ist
  prefill-lastig, daher zählt für ihn v.a. Modellgröße/Prompt-Chunking, weniger die Decode-tok/s.

---

## Empfehlung (gestuft)

**(a) Beste Genauigkeit:** Bei der **Gemma-Instruct-Familie** bleiben — sie ist als einzige
nachweislich genau auf deutsche PERSON/FIRMA **und** deckt Art.9 per Prompt ab. (gemma-4-31b ist
heute genau, nur langsam.)

**(b) Bester Genauigkeit/Latenz-Kompromiss (zu testen):** **gemma-3-27b-it-qat-4bit** oder
**gemma-3-12b-it** — gleiche Lineage, kleiner → schnellerer Prefill, MLX-ready. *Validierung läuft:*
beide werden gerade gezogen und mit demselben Benchmark gegen die Baseline gemessen; freigeben nur,
wenn PERSON/FIRMA/ORT-Recall **und** Art.9-Block die Baseline halten.

**(c) Dediziertes NER-Modell:** **Nein** für volle Abdeckung. Höchstens als Hybrid-Vorfilter
(GLiNER2-PII 0,3B für generische PII-Latenz) — Preis: zweite Python-Pipeline + Union-Logik;
angesichts des funktionierenden Chunkings **nicht** den Aufwand wert.

---

## Konkrete nächste Schritte

1. **DRINGEND (Leak):** Regex-Detektoren `creditcard.ts` (Luhn) + `apikey.ts` ergänzen + Tests.
   Schließt die Kreditkarten/API-Key-Lücke modell-unabhängig.
2. **Latenz:** Sobald gemma-3-27b-qat / 12b geladen sind: `./run_bench.sh "<id-27b>" "<id-12b>"`
   und gegen die Baseline-Tabelle vergleichen; bei gehaltener Genauigkeit auf das kleinste Modell,
   das Recall+Art.9 hält, wechseln (`PII_PROXY_CLASSIFIER_MODEL` in `~/.pii-proxy.env` + Reinstall).
3. **ORT-Schwäche:** Straßen-ohne-PLZ ("Bahnhofstraße 5") werden inkonsistent erkannt — Classifier-
   Prompt um explizite STRASSE/ADRESSE-Beispiele schärfen oder Straßen-Regex ergänzen.
4. **Benchmark-Set erweitern:** aktuell 25 synthetische Fälle — für belastbare Aussagen auf
   50–100 Fälle (mehr Namensvarianten, Dialekt, Tippfehler, verschachtelte Art.9) ausbauen.

> Harness wiederverwendbar: `opensource/pii-proxy/bench/de-pii-bench/` (cases.py · runner.py · run_bench.sh).
