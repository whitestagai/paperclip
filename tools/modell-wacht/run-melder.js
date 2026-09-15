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
const { existsSync } = require('fs');
const path = require('path');

// Bewusst NICHT fest /usr/bin/python3: das ist Apples Shim auf die Command
// Line Tools. Nach einem Xcode-Update gilt dessen Lizenz als nicht akzeptiert
// und JEDER Aufruf bricht mit Exit 69 ab, bevor eine Zeile Python läuft. Am
// 15.09.2026 hat genau das die Aufsicht ab 04:29 lautlos stillgelegt — nach
// einem Xcode-Update um 04:24. Ein Wächter, der schweigend ausfällt, ist
// schlimmer als keiner: er erzeugt die Gewissheit, dass jemand hinsieht.
//
// Homebrew-Python hängt nicht an dieser Lizenz. Der Shim bleibt als Rückfall,
// falls Homebrew fehlt. Die Skripte sind 3.9-kompatibel geschrieben und laufen
// damit unter beiden (gegengeprüft: 37 Tests unter 3.14.6 grün).
const PYTHON = ['/opt/homebrew/bin/python3', '/usr/bin/python3'].find(existsSync);
if (!PYTHON) {
  console.error('Melder nicht startbar: kein python3 gefunden.');
  process.exit(1);
}

const skript = path.join(__dirname, 'melder.py');
const r = spawnSync(PYTHON, [skript, ...process.argv.slice(2)], {
  stdio: 'inherit',
  cwd: __dirname,          // damit `import pruefung` / `import waechter` greift
  env: process.env,
});

if (r.error) {
  console.error('Melder nicht startbar:', r.error.message);
  process.exit(1);
}
process.exit(r.status === null ? 1 : r.status);
