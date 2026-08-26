// Einstiegspunkt des Modell-Aufsicht-Melders für launchd.
//
// Gleicher Grund wie bei tools/backup-waechter: macOS verweigert einem
// launchd-Job aus zsh/bash/python den Zugriff auf die SynologyDrive-Freigabe —
// der Mount ist sichtbar, Lesen scheitert mit „Operation not permitted" (TCC).
// node hat die Berechtigung und vererbt sie an Kindprozesse.
//
// Ohne diesen Umweg sind zwei Quellen (Obsidian-Tagger-Templates und
// Wake-Satellit) unlesbar. Der Wächter ist fail-closed, meldet das also als
// zwei harte Befunde — und der Melder macht daraus ein Fehlalarm-Issue.
// Beim ersten Probelauf am 26.08. ist genau das passiert.
//
// node ist reiner Türöffner und enthält bewusst keine Logik.
const { spawnSync } = require('child_process');
const path = require('path');

const skript = path.join(__dirname, 'melder.py');
const r = spawnSync('/usr/bin/python3', [skript, ...process.argv.slice(2)], {
  stdio: 'inherit',
  cwd: __dirname,          // damit `import pruefung` / `import waechter` greift
  env: process.env,
});

if (r.error) {
  console.error('Melder nicht startbar:', r.error.message);
  process.exit(1);
}
process.exit(r.status === null ? 1 : r.status);
