// Nächtlicher Wächter: findet Dateien, die Synology Drive ausgelagert hat
// („dataless" — sichtbar, aber Inhalt nur noch auf dem NAS).
//
// Warum: Am 08.10.2026 hatte Synology nachts Tausende Dateien aus dem
// Paperclip-Repo, node_modules, dem lmstudio-Adapter und dem PII-Proxy
// ausgelagert. Laufende Dienste merkten nichts — erst beim nächsten Neustart
// scheiterte jeder Start mit EAGAIN (-11). Paperclip war 7 h down, am 09.10.
// nach einem Neustart erneut. Seit dem 10.10. ist „Claude Code MAC" in
// Synology angeheftet; dieser Wächter prüft, dass das hält.
//
// node ist Türöffner: macOS (TCC) verweigert launchd-Jobs aus bash/python den
// Zugriff auf den Cloud-Ordner, node darf und vererbt das an `find`.
// Prüft mit der Systemerkennung (`find -flags +dataless`), keine Heuristik.
// Mail nur bei Fund (Absender/Empfänger wie beim Backup-Wächter).
'use strict';
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const WURZEL = path.join(os.homedir(), 'Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC');
const LIVE = ['Paperclip', 'opensource/paperclip-adapter-lmstudio', 'opensource/pii-proxy', 'Apps'];
const MAILHUB_URL = 'http://127.0.0.1:5678/webhook/mailhub/send';
const MAILHUB_ENV = path.join(os.homedir(), '.paperclip/instances/default/secrets/mailhub.env');
const LOG = path.join(os.homedir(), '.paperclip/logs/dataless-waechter.log');

function log(z) {
  const t = new Date(); const pad = (n) => String(n).padStart(2, '0');
  const zeile = `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())} ${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}  ${z}\n`;
  process.stdout.write(zeile);
  try { fs.appendFileSync(LOG, zeile); } catch { /* Log ist Komfort */ }
}

function suche(ordner) {
  const r = spawnSync('/usr/bin/find', [ordner, '-type', 'f', '-flags', '+dataless'],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 15 * 60 * 1000 });
  if (r.error || (r.status !== 0 && !r.stdout)) {
    return { fehler: (r.error && r.error.message) || (r.stderr || '').trim().slice(0, 300) || `Exit ${r.status}` };
  }
  return { dateien: r.stdout.split('\n').filter(Boolean) };
}

async function mail(betreff, text) {
  let secret;
  try {
    const z = fs.readFileSync(MAILHUB_ENV, 'utf8').split('\n').find((l) => l.startsWith('MAILHUB_SECRET='));
    secret = z.split('=').slice(1).join('=').trim().replace(/^"|"$/g, '');
  } catch (e) { log(`Mailhub-Secret nicht lesbar: ${e.message}`); return; }
  const html = `<pre style="font-family:Menlo,monospace;font-size:12px">${text.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`;
  try {
    const res = await fetch(MAILHUB_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Mailhub-Secret': secret },
      body: JSON.stringify({ from: 'cto@whitestag.ai', to: 'ws@whitestag.ai', subject: betreff, text, html }),
      signal: AbortSignal.timeout(30000),
    });
    log(`Mail gesendet (HTTP ${res.status}): ${betreff}`);
  } catch (e) { log(`Mail konnte NICHT gesendet werden: ${e.message}`); }
}

(async () => {
  const funde = []; const fehler = [];
  for (const rel of LIVE) {
    const ordner = path.join(WURZEL, rel);
    if (!fs.existsSync(ordner)) continue;
    const r = suche(ordner);
    if (r.fehler) { fehler.push(`${rel}: ${r.fehler}`); continue; }
    log(`${rel}: ${r.dateien.length} ausgelagert`);
    for (const d of r.dateien) funde.push(path.relative(WURZEL, d));
  }
  if (!funde.length && !fehler.length) { log('Alles lokal.'); return; }
  const gruppen = {};
  for (const f of funde) { const k = f.split('/').slice(0, 3).join('/'); gruppen[k] = (gruppen[k] || 0) + 1; }
  const text = [
    funde.length ? `${funde.length} Datei(en) in Live-Pfaden sind von Synology ausgelagert (dataless).` : '',
    'Laufende Dienste merken das erst beim nächsten Neustart — dann scheitert er mit EAGAIN (-11).',
    '', 'Nach Ordner:', ...Object.entries(gruppen).sort((a, b) => b[1] - a[1]).slice(0, 25).map(([k, n]) => `  ${String(n).padStart(6)}  ${k}`),
    ...(fehler.length ? ['', 'Nicht prüfbar:', ...fehler.map((f) => `  ${f}`)] : []),
    '', 'Prüfen: Ist „Claude Code MAC" in Synology noch angeheftet (Rechtsklick → Lokale Kopie dauerhaft anheften)?',
    'Rettung siehe Gedächtnis-Notiz project_synology_dataless_ausfall.',
  ].filter((z, i) => z !== '' || i > 0).join('\n');
  log(funde.length ? `ALARM: ${funde.length} ausgelagert` : `ALARM: ${fehler.length} Ordner nicht prüfbar`);
  await mail(funde.length ? `ALARM: ${funde.length} Dateien von Synology ausgelagert` : 'ALARM: Auslagerungs-Prüfung nicht möglich', text);
  process.exitCode = 1;
})();
