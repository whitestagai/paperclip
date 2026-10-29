// de.whitestag.vault-tagger-clara -- nächtlicher Frontmatter-Tagger für den Clara-Vault
//
// Gegenstück zu vault-tagger-nightly.sh (WHITESTAG), aber als node-Job: Ein
// zsh-launchd-Job kommt nicht an SMB-Inhalte, node schon — und Kindprozesse
// (hier python) erben diesen Zugriff. Genau so liest sync-clara-mirror.js den Vault.
//
// Läuft täglich 01:30, vor dem Clara-Vault-Maintainer (Routine 02:00). Der Agent
// startet den Tagger NICHT selbst (shell_exec cappt bei 120 s, allein der Scan über
// SMB dauert ~40 s) — er liest nur ~/.paperclip/logs/vault-tagger-clara-last.json.
//
// Geschrieben wird direkt auf das NAS, nie in den lokalen Spiegel
// (~/.paperclip/clara-vault-mirror ist read-only und wird per rsync --delete überschrieben).
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const VAULT = '/Volumes/homes/cw/Obsidian/Clara-Vault';
const TAGGER_DIR = '/Users/walterschoenenbroecher.de/Library/CloudStorage/SynologyDrive-Mac/Claude Code MAC/Paperclip/obsidian-tagger';
const TEMPLATE = path.join(TAGGER_DIR, 'templates/frontmatter-template-clara.yaml');
const PENDING = path.join(TAGGER_DIR, 'pending_tags_clara.yaml');
const LOGDIR = path.join(os.homedir(), '.paperclip/logs');
const LOG = path.join(LOGDIR, 'vault-tagger-clara.log');
const STATUS = path.join(LOGDIR, 'vault-tagger-clara-last.json');
const MAILHUB_URL = 'http://127.0.0.1:5678/webhook/mailhub/send';
const MAILHUB_ENV = path.join(os.homedir(), '.paperclip/instances/default/secrets/mailhub.env');
const LIMIT = '200';
const TIMEOUT_MS = 60 * 60 * 1000;

const ts = () => new Date().toLocaleString('sv-SE', { timeZone: 'Europe/Berlin' });
const logline = (m) => { try { fs.appendFileSync(LOG, m + '\n'); } catch (e) {} };

function writeStatus(fields) {
  const status = { timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), vault: VAULT, ...fields };
  fs.writeFileSync(STATUS, JSON.stringify(status, null, 2) + '\n');
}

async function alertMail(subject, body) {
  let secret = '';
  try {
    const m = fs.readFileSync(MAILHUB_ENV, 'utf8').match(/^MAILHUB_SECRET=(.*)$/m);
    secret = m ? m[1].trim() : '';
  } catch (e) {}
  if (!secret) { logline(ts() + ' Hinweis: kein MAILHUB_SECRET — keine Fehler-Mail'); return; }
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
    logline(ts() + ' Fehler-Mail: HTTP ' + res.status);
  } catch (e) { logline(ts() + ' Fehler-Mail gescheitert: ' + e.message); }
}

async function main() {
  fs.mkdirSync(LOGDIR, { recursive: true });
  logline('===== ' + ts() + ' Vault-Tagger Clara Start');

  // Quelle lesbar? Ohne NAS ist keine Aussage über den Vault möglich.
  try { fs.readdirSync(path.join(VAULT, 'Kontakte')); }
  catch (e) {
    const msg = 'Clara-Vault nicht lesbar (' + e.code + ') — NAS-Mount /Volumes/homes prüfen.';
    logline(ts() + ' ABBRUCH: ' + msg);
    writeStatus({ exit_code: 3, gefunden: null, report_path: '', fertig: '', fehler: msg });
    await alertMail('Vault-Tagger Clara: Vault nicht lesbar', msg);
    return;
  }

  const r = spawnSync(path.join(TAGGER_DIR, '.venv/bin/python'), [
    path.join(TAGGER_DIR, 'tagger.py'),
    '--vault', VAULT, '--template', TEMPLATE, '--pending-file', PENDING,
    '--apply', '--limit', LIMIT, '--report',
  ], { encoding: 'utf8', timeout: TIMEOUT_MS, maxBuffer: 32 * 1024 * 1024 });

  const out = (r.stdout || '') + (r.stderr || '');
  logline(out.trimEnd());
  // status ist null, wenn der Prozess per Signal endete (z. B. Timeout)
  const exitCode = r.status === null ? 124 : r.status;
  logline('===== ' + ts() + ' Vault-Tagger Clara Ende (exit ' + exitCode + (r.signal ? ', signal ' + r.signal : '') + ')');

  const lines = out.split('\n');
  const last = (re) => { for (let i = lines.length - 1; i >= 0; i--) if (re.test(lines[i])) return lines[i]; return ''; };
  const reportPath = last(/^REPORT_PATH=/).replace(/^REPORT_PATH=/, '');
  const fertig = last(/Fertig\. ok=/);
  const gefundenMatch = last(/Gefunden ohne Frontmatter:/).match(/Gefunden ohne Frontmatter:\s*(\d+)/);

  writeStatus({
    exit_code: exitCode,
    gefunden: gefundenMatch ? Number(gefundenMatch[1]) : null,
    report_path: reportPath,
    fertig,
    ...(r.error ? { fehler: r.error.message } : {}),
  });

  if (exitCode !== 0) {
    await alertMail('Vault-Tagger Clara: Nachtlauf fehlgeschlagen (exit ' + exitCode + ')', lines.slice(-20).join('\n'));
  }
}

main();
