# vault-tagger-clara

Nächtlicher Frontmatter-Tagger für den Clara-Vault (`/Volumes/homes/cw/Obsidian/Clara-Vault`).
Gegenstück zu `vault-tagger-nightly.sh` (WHITESTAG), seit 2026-10-29.

| Was | Wo |
|---|---|
| Dienst | launchd `de.whitestag.vault-tagger-clara`, täglich 01:30 |
| Skript live | `~/.paperclip/scripts/vault-tagger-clara/vault-tagger-clara.js` |
| Status für den Agenten | `~/.paperclip/logs/vault-tagger-clara-last.json` |
| Log | `~/.paperclip/logs/vault-tagger-clara.log` |
| Report | `<Vault>/Paperclip/_Meta/Vault-Tagger-Reports/` |
| Agent | Clara Sound / Vault-Maintainer `500a1656`, Routine „Clara-Vault-Pflege" 02:00 |
| Strukturprüfung | `tools/vault-pruefer-clara/` (01:45) — der Agent berichtet beide Dienste in einem Kommentar |

**Warum node statt zsh:** Ein zsh-launchd-Job kommt nicht an SMB-Inhalte, node schon; der
gestartete python-Tagger erbt den Zugriff.

**Warum nicht der Agent selbst:** `shell_exec` cappt bei 120 s, allein der Scan über SMB dauert
~40 s. Der Agent liest nur die Status-Datei und muss deren Rohwerte zitieren
(`AGENTS.clara-vault-maintainer.md`, eingespielt per `PUT /api/agents/:id/instructions-bundle/file`).
Ohne diese Belegpflicht hat er vom 22.08. bis 03.10.2026 Erfolge erfunden.

`exit_code` in der Status-Datei: 0 ok · 1 einzelne Dateien fehlgeschlagen · 2 Template/Vault fehlt ·
3 NAS nicht lesbar · 124 Timeout (60 min). Bei ≠ 0 geht eine Mail an ws@.

Deploy:

```bash
cp vault-tagger-clara.js ~/.paperclip/scripts/vault-tagger-clara/
cp de.whitestag.vault-tagger-clara.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/de.whitestag.vault-tagger-clara 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/de.whitestag.vault-tagger-clara.plist
```
