# vault-pruefer-clara

Nächtliche Strukturprüfung für den Clara-Vault (`/Volumes/homes/cw/Obsidian/Clara-Vault`), seit 2026-10-31.
Konzept: `docs/superpowers/specs/2026-10-31-vault-pruefer-clara-design.md`.

| Was | Wo |
|---|---|
| Dienst | launchd `de.whitestag.vault-pruefer-clara`, täglich 01:45 |
| Skript live | `~/.paperclip/scripts/vault-pruefer-clara/vault-pruefer-clara.js` (+ `lib/`, `node_modules/`) |
| Lesequelle | Spiegel `~/.paperclip/clara-vault-mirror` + Index-DB `paperclip_brain_clara` |
| Status für den Agenten | `~/.paperclip/logs/vault-pruefer-clara-last.json` |
| Bericht | `<Vault>/Paperclip/_Meta/Vault-Pruefer-Reports/<datum>.md` |
| Vollständige Listen | `~/.paperclip/state/vault-pruefer-clara/<datum>/P<n>.txt` |
| Vortag (für Δ) | `~/.paperclip/state/vault-pruefer-clara/letzter-stand.json` |
| Agent | Clara Sound / Vault-Maintainer `500a1656`, Routine „Clara-Vault-Pflege" 02:00 |

Prüfungen: P1 Frontmatter vom Index nicht lesbar · P2 fehlt im Index / keine Chunks · P3 `typ` ·
P4 `status` · P5 `tags` · P6 tote Wikilinks (echt / Import-Rest) · P7 gleiche Namen
(inhaltsgleich / nur Name) · P8 über 2 MB, leer, Wurzel. Stufen und Quellen in `lib/pruefungen.js`.

Der Prüfer **ändert keine Notiz**. Korrekturen laufen nur nach Liste und Freigabe (zweite Ausbaustufe).

`exit_code` in der Status-Datei: 0 ok · 1 unerwarteter Fehler · 3 Spiegel veraltet (letztes `OK` in
`clara-mirror-sync.log` älter als 60 min) · 4 Index-DB nicht erreichbar (P2 = `null`, Rest läuft) ·
124 Timeout (30 min). Bei ≠ 0 geht eine Mail an ws@.

Der Timeout greift erst nach dem Einlesen: Scan und Prüfungen laufen synchron (~3 s für
17.500 Notizen auf dem lokalen Spiegel). Ein hängender Dateizugriff würde den Lauf
blockieren — beim lokalen Spiegel bewusst in Kauf genommen.

`letzter-stand.json` hält `{ vortag, heute }`: Ein zweiter Lauf am selben Tag vergleicht
weiter mit dem Vortag. Tageslisten älter als 30 Tage werden beim Lauf entfernt.

Tests: `npm test` (node --test, keine Datenbank nötig).

Deploy:

```bash
mkdir -p ~/.paperclip/scripts/vault-pruefer-clara
cp -R vault-pruefer-clara.js lib package.json package-lock.json ~/.paperclip/scripts/vault-pruefer-clara/
(cd ~/.paperclip/scripts/vault-pruefer-clara && npm ci --omit=dev)
cp de.whitestag.vault-pruefer-clara.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/de.whitestag.vault-pruefer-clara 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.whitestag.vault-pruefer-clara.plist
```
