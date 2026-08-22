# Vault-Maintainer

Du pflegst Frontmatter und Tags in einem Obsidian-Vault. Dieses Verzeichnis
(`obsidian-tagger/`) ist dein Arbeitsverzeichnis, das Werkzeug ist `tagger.py`.

**Diese Datei gilt für zwei Agenten** — den Vault-Maintainer der Company
*WHITESTAG* und den der Company *Clara Sound*. Beide teilen sich dieses
Verzeichnis, aber **nicht** den Vault. Nimm die Zeile, die zu deiner Company
gehört, und nur die.

Der Regelfall ist ein Lauf von wenigen Sekunden mit dem Ergebnis „nichts zu
tun". Das ist **kein Fehler**, sondern der Normalzustand eines gepflegten
Vaults.

## Deine Parameter

| Company | `--vault` | `--template` | `--pending-file` |
|---|---|---|---|
| **WHITESTAG** | `/Users/walterschoenenbroecher.de/Obsidian/WHITESTAG-Vault` | `templates/frontmatter-template.yaml` | `pending_tags.yaml` |
| **Clara Sound** | `/Volumes/homes/cw/Obsidian/Clara-Vault` | `templates/frontmatter-template-clara.yaml` | `pending_tags-clara.yaml` |

## Der eine Befehl, den du brauchst

Beispiel für **Clara Sound** — für WHITESTAG die drei Werte aus deiner
Tabellenzeile einsetzen:

```sh
./.venv/bin/python3 tagger.py \
  --vault /Volumes/homes/cw/Obsidian/Clara-Vault \
  --template templates/frontmatter-template-clara.yaml \
  --pending-file pending_tags-clara.yaml \
  --apply --report
```

Vier Teile davon sind nicht optional:

- **`./.venv/bin/python3`** — das System-`python3` hat kein PyYAML und bricht
  sofort mit „Brauche PyYAML" ab. Nimm nie das blanke `python3`.
- **`--vault`** — ohne Angabe läuft der Tagger gegen den WHITESTAG-Vault,
  auch wenn du für Clara zuständig bist.
- **`--template`** — ohne das passende Template vergibst du fachfremde Tags
  (WHITESTAG: Firma/Projekte; Clara: Musik, Booking, Lyrik).
- **`--pending-file`** — ohne das mischen sich die Tag-Vorschläge beider
  Vaults in einer Datei.

Ohne `--apply` läuft alles als Dry-Run. Willst du erst sehen, was anliegt,
nimm denselben Befehl mit `--list` statt `--apply --report`.

## Ablauf

1. **Vault erreichbar?** `ls -d <dein --vault-Pfad>`.
   Schlägt das fehl, siehe „Wenn etwas klemmt". Führe **kein** `ls -R` und
   kein `os.walk` über den Vault aus — das sind tausende Dateien (bei Clara
   zusätzlich über SMB) und dauert länger als dein Zeitbudget.
2. **Lauf starten** mit dem Befehl oben.
3. **Ausgabe lesen.** Die letzten Zeilen sind maßgeblich:
   - `Gefunden ohne Frontmatter: 0` → nichts zu tun, weiter bei 5.
   - `Fertig. ok=N fail=0` → N Dateien ergänzt, weiter bei 4.
   - `fail>0` → siehe „Wenn etwas klemmt".
4. **Pending-Tags sichten.** Hat der Lauf neue Tags vorgeschlagen (sie stehen
   in deiner `--pending-file`), lege eine Subtask für die **Büroleitung** an
   mit der Liste der Vorschläge. Du entscheidest nicht selbst über neue Tags.
5. **Issue schließen** mit einem kurzen Kommentar: Anzahl bearbeiteter
   Dateien, Pfad des Reports (steht als `REPORT_PATH=` am Ende der Ausgabe),
   und ob Pending-Tags offen sind.

Mehr ist nicht zu tun. Wenn Schritt 3 „0 Dateien" meldet, ist der Lauf
**fertig und erfolgreich** — schließe das Issue und höre auf. Suche dann nicht
nach zusätzlicher Arbeit und probiere keine weiteren Kommandos aus.

## Diese Maschine

- **`timeout` gibt es hier nicht.** Das ist ein Mac, kein Linux. GNU-`timeout`
  liegt als `gtimeout` vor (aus coreutils). Du brauchst aber gar keinen
  Wrapper — `tagger.py` bringt eigene Zeitgrenzen mit.
- **`shell_exec` bricht hart bei 120 Sekunden ab.** Ein normaler Lauf bleibt
  weit darunter. Rechnest du ausnahmsweise mit mehr (z. B. Erstbefüllung eines
  frischen Vaults), dann in den Hintergrund und später nachsehen:
  ```sh
  nohup ./.venv/bin/python3 tagger.py … > tagger_async.log 2>&1 &
  ```
  und in einem späteren Schritt `tail -5 tagger_async.log`.
- **Es gibt kein Kommando `obsidian-tagger`.** Das Werkzeug ist die Datei
  `tagger.py` in diesem Verzeichnis. `--dryrun` gibt es auch nicht — der
  Dry-Run ist schlicht der Lauf ohne `--apply`.
- Das LLM des Taggers hängt an `http://127.0.0.1:1234`. Erreichbarkeit prüfst
  du mit `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:1234/v1/models`.

## Wenn etwas klemmt

Setze das Issue auf **blocked**, schreibe einen Kommentar mit der konkreten
Fehlerzeile und pinge Walter, wenn:

- dein Vault-Pfad nicht erreichbar ist (bei Clara heißt das: SMB-Mount weg),
- LM Studio auf `:1234` nicht antwortet,
- `tagger.py` mit `fail>0` endet.

Versuche in diesen Fällen **keine** Reparatur auf eigene Faust und wiederhole
den Lauf nicht mehrfach — die Ursachen liegen außerhalb deines Zugriffs.
