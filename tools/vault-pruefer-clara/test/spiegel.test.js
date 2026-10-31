const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spiegelAktuell } = require('../lib/spiegel');
const { main } = require('../vault-pruefer-clara');

const JETZT = new Date('2026-11-01T00:45:00Z');
// Gleiches Format wie sync-clara-mirror.js
const berlin = (d) => d.toLocaleString('sv-SE', { timeZone: 'Europe/Berlin' });
const okZeile = (minutenAlt) => `${berlin(new Date(JETZT - minutenAlt * 60000))}  OK (node): 17574 .md gespiegelt.`;

test('spiegelAktuell: OK-Zeile 10 Minuten alt ist aktuell', () => {
  assert.equal(spiegelAktuell(okZeile(10) + '\n', JETZT).ok, true);
});

test('spiegelAktuell: späterer Abbruch nach frischem OK bleibt aktuell', () => {
  const log = okZeile(20) + '\n' + `${berlin(new Date(JETZT - 5 * 60000))}  ABBRUCH: Quelle nicht lesbar (ENOENT) — Mirror unveraendert.\n`;
  assert.equal(spiegelAktuell(log, JETZT).ok, true);
});

test('spiegelAktuell: OK-Zeile 90 Minuten alt ist veraltet', () => {
  const r = spiegelAktuell(okZeile(90) + '\n', JETZT);
  assert.equal(r.ok, false);
  assert.match(r.grund, /90/);
});

test('spiegelAktuell: nur Abbrüche, leer oder Müll ist nicht aktuell', () => {
  assert.equal(spiegelAktuell('2026-11-01 01:40:00  ABBRUCH: x\n', JETZT).ok, false);
  assert.equal(spiegelAktuell('', JETZT).ok, false);
  assert.equal(spiegelAktuell('\u0000\u0001 kaputt', JETZT).ok, false);
});

function umgebung(logText) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpc-main-'));
  const logDatei = path.join(dir, 'sync.log');
  fs.writeFileSync(logDatei, logText);
  const mails = [];
  return {
    dir,
    mails,
    opts: {
      spiegel: path.join(__dirname, 'fixtures', 'vault'),
      vorlage: path.join(__dirname, 'fixtures', 'vorlage.yaml'),
      logDatei,
      statusDatei: path.join(dir, 'status.json'),
      stateDir: path.join(dir, 'state'),
      berichtDir: path.join(dir, 'bericht'),
      dbUrl: 'postgres://niemand@127.0.0.1:1/keine',
      jetzt: JETZT,
      mail: async (betreff, text) => mails.push({ betreff, text }),
    },
  };
}

test('main gegen Fixtures: Index nicht erreichbar ergibt exit 4, Rest läuft', async () => {
  const u = umgebung(okZeile(10) + '\n');
  await main(u.opts);
  const s = JSON.parse(fs.readFileSync(u.opts.statusDatei, 'utf8'));
  assert.equal(s.exit_code, 4);
  assert.equal(s.pruefungen.P2.anzahl, null);
  assert.equal(s.pruefungen.P1.anzahl, 1);
  assert.equal(s.report_path, path.join(u.opts.berichtDir, '2026-11-01.md'));
  assert.ok(fs.existsSync(s.report_path));
  assert.ok(fs.existsSync(path.join(u.opts.stateDir, '2026-11-01', 'P1.txt')));
  assert.ok(fs.existsSync(path.join(u.opts.stateDir, 'letzter-stand.json')));
  assert.equal(u.mails.length, 1);
});

test('main mit veraltetem Spiegel: exit 3, kein Bericht', async () => {
  const u = umgebung(okZeile(90) + '\n');
  await main(u.opts);
  const s = JSON.parse(fs.readFileSync(u.opts.statusDatei, 'utf8'));
  assert.equal(s.exit_code, 3);
  assert.ok(!fs.existsSync(u.opts.berichtDir));
  assert.ok(!fs.existsSync(path.join(u.opts.stateDir, 'letzter-stand.json')));
  assert.equal(u.mails.length, 1);
});
