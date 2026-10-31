// de.whitestag.vault-pruefer-clara -- nächtliche Strukturprüfung des Clara-Vaults
//
// Läuft täglich 01:45, zwischen dem Tagger (01:30) und dem Clara-Vault-Maintainer
// (Routine 02:00). Der Agent prüft NICHT selbst — er liest nur
// ~/.paperclip/logs/vault-pruefer-clara-last.json und zitiert deren Rohwerte.
// Ohne diese Belegpflicht hat er vom 22.08. bis 03.10.2026 Erfolge erfunden.
//
// Gelesen wird der lokale Spiegel (schnell, keine SMB-Timeouts), geschrieben nur
// der Bericht auf das NAS. Der Prüfer ändert keine Notiz.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { ladeVorlage, ladeNotizen } = require('./lib/lesen');
const { pruefe } = require('./lib/pruefungen');
const { vergleicheIndex, ladeIndex } = require('./lib/index-abgleich');
const { baueStatus, baueBericht, schreibeListen } = require('./lib/ausgabe');
const { spiegelAktuell } = require('./lib/spiegel');

const HOME = os.homedir();
const STANDARD = {
  spiegel: path.join(HOME, '.paperclip/clara-vault-mirror'),
  vorlage: '/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip/obsidian-tagger/templates/frontmatter-template-clara.yaml',
  logDatei: path.join(HOME, '.paperclip/logs/clara-mirror-sync.log'),
  statusDatei: path.join(HOME, '.paperclip/logs/vault-pruefer-clara-last.json'),
  stateDir: path.join(HOME, '.paperclip/state/vault-pruefer-clara'),
  berichtDir: '/Volumes/homes/cw/Obsidian/Clara-Vault/Paperclip/_Meta/Vault-Pruefer-Reports',
  dbUrl: process.env.BRAIN_DATABASE_URL || 'postgres://walterschoenenbroecher.de@localhost:5432/paperclip_brain_clara',
};
const TIMEOUT_MS = 30 * 60 * 1000;
const MAILHUB_URL = 'http://127.0.0.1:5678/webhook/mailhub/send';
const MAILHUB_ENV = path.join(HOME, '.paperclip/instances/default/secrets/mailhub.env');

const datumBerlin = (d) => d.toLocaleString('sv-SE', { timeZone: 'Europe/Berlin' }).slice(0, 10);

async function mailhub(subject, body) {
  let secret = '';
  try {
    const m = fs.readFileSync(MAILHUB_ENV, 'utf8').match(/^MAILHUB_SECRET=(.*)$/m);
    secret = m ? m[1].trim() : '';
  } catch (e) {}
  if (!secret) { console.error('Hinweis: kein MAILHUB_SECRET — keine Fehler-Mail'); return; }
  try {
    const res = await fetch(MAILHUB_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Mailhub-Secret': secret },
      body: JSON.stringify({
        from: 'cto@whitestag.ai', to: 'ws@whitestag.ai', subject,
        text: body, html: '<pre>' + body.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</pre>', attachments: [],
      }),
      signal: AbortSignal.timeout(20000),
    });
    console.log('Fehler-Mail: HTTP ' + res.status);
  } catch (e) { console.error('Fehler-Mail gescheitert: ' + e.message); }
}

function schreibeJson(datei, daten) {
  fs.mkdirSync(path.dirname(datei), { recursive: true });
  fs.writeFileSync(datei, JSON.stringify(daten, null, 2) + '\n');
}

async function pruefen(o, jetzt) {
  let logText = '';
  try { logText = fs.readFileSync(o.logDatei, 'utf8'); } catch (e) {}
  const spiegel = spiegelAktuell(logText, jetzt);
  if (!spiegel.ok) {
    return { abbruch: { exit_code: 3, fehler: 'Spiegel nicht verwendbar: ' + spiegel.grund } };
  }

  const vorlage = ladeVorlage(o.vorlage);
  const notizen = ladeNotizen(o.spiegel);
  const befunde = pruefe(notizen, vorlage);
  let exitCode = 0;
  let fehler;
  try {
    befunde.P2 = vergleicheIndex(notizen, await ladeIndex(o.dbUrl));
  } catch (e) {
    befunde.P2 = null;
    exitCode = 4;
    fehler = 'Index-DB nicht erreichbar: ' + e.message;
  }
  return { befunde, notizen, exitCode, fehler };
}

async function main(opts = {}) {
  const o = { ...STANDARD, mail: mailhub, ...opts };
  const jetzt = o.jetzt || new Date();
  const datum = datumBerlin(jetzt);
  const zeitstempel = jetzt.toISOString().replace(/\.\d{3}Z$/, 'Z');

  let ergebnis;
  let timer;
  try {
    ergebnis = await Promise.race([
      pruefen(o, jetzt),
      new Promise((_, nein) => { timer = setTimeout(() => nein(new Error('Timeout')), TIMEOUT_MS); }),
    ]);
  } catch (e) {
    const timeout = e.message === 'Timeout';
    ergebnis = { abbruch: { exit_code: timeout ? 124 : 1, fehler: timeout ? 'Lauf länger als 30 min' : e.message } };
  } finally {
    clearTimeout(timer);
  }

  if (ergebnis.abbruch) {
    const status = { timestamp: zeitstempel, ...ergebnis.abbruch, report_path: '' };
    schreibeJson(o.statusDatei, status);
    await o.mail(`Vault-Prüfer Clara: Lauf abgebrochen (exit ${status.exit_code})`, status.fehler);
    return status;
  }

  const { befunde, notizen, exitCode, fehler } = ergebnis;
  const letzterStand = path.join(o.stateDir, 'letzter-stand.json');
  let vorher = null;
  try { vorher = JSON.parse(fs.readFileSync(letzterStand, 'utf8')); } catch (e) {}

  const reportPath = path.join(o.berichtDir, `${datum}.md`);
  const status = baueStatus({ befunde, vorher, notizenGesamt: notizen.length, exitCode, reportPath, zeit: jetzt });
  if (fehler) status.fehler = fehler;

  schreibeListen(befunde, path.join(o.stateDir, datum));
  fs.mkdirSync(o.berichtDir, { recursive: true });
  fs.writeFileSync(reportPath, baueBericht(status, befunde, datum));
  schreibeJson(o.statusDatei, status);
  schreibeJson(letzterStand, status);

  if (exitCode !== 0) await o.mail(`Vault-Prüfer Clara: Lauf unvollständig (exit ${exitCode})`, fehler);
  return status;
}

module.exports = { main };

if (require.main === module) {
  main().then(
    (s) => console.log(`Vault-Prüfer Clara: exit_code ${s.exit_code}, Bericht ${s.report_path || '–'}`),
    (e) => { console.error('Vault-Prüfer Clara: fataler Fehler:', e); process.exitCode = 1; },
  );
}
