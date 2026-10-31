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

test('spiegelAktuell: Nacht der Sommerzeit-Umstellung ergibt das echte Alter', () => {
  // 28.03.2027: 02:00 CET springt auf 03:00 CEST. 01:30 CET = 00:30Z, Prüfung um 00:45Z.
  const r = spiegelAktuell('2027-03-28 01:30:00  OK (node): 1 .md gespiegelt.\n', new Date('2027-03-28T00:45:00Z'));
  assert.equal(r.ok, true);
  assert.match(r.grund, /vor 15 min/);
});

test('spiegelAktuell: OK-Zeile aus der Zukunft ist nicht aktuell', () => {
  const r = spiegelAktuell(okZeile(-60) + '\n', JETZT);
  assert.equal(r.ok, false);
  assert.match(r.grund, /Zukunft/);
});

test('main: zweiter Lauf am selben Tag vergleicht weiter mit dem Vortag', async () => {
  const u = umgebung(okZeile(10) + '\n');
  fs.mkdirSync(u.opts.stateDir, { recursive: true });
  // Vortag: 3 P1-Befunde. Heute 1 → Delta −2, auch beim zweiten Lauf heute.
  const vortag = { timestamp: '2026-10-31T00:45:00Z', pruefungen: { P1: { anzahl: 3, delta_vortag: null, stufe: 'hoch' } } };
  fs.writeFileSync(path.join(u.opts.stateDir, 'letzter-stand.json'), JSON.stringify(vortag));
  await main(u.opts);
  await main(u.opts);
  const s = JSON.parse(fs.readFileSync(u.opts.statusDatei, 'utf8'));
  assert.equal(s.pruefungen.P1.delta_vortag, -2);
});

test('main: Tageslisten älter als 30 Tage werden entfernt', async () => {
  const u = umgebung(okZeile(10) + '\n');
  for (const d of ['2026-09-30', '2026-10-05', 'nicht-loeschen']) fs.mkdirSync(path.join(u.opts.stateDir, d), { recursive: true });
  await main(u.opts);
  const rest = fs.readdirSync(u.opts.stateDir).sort();
  assert.ok(!rest.includes('2026-09-30'));
  assert.ok(rest.includes('2026-10-05'));
  assert.ok(rest.includes('nicht-loeschen'));
  assert.ok(rest.includes('2026-11-01'));
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

test('main: Bericht nicht schreibbar ergibt exit 3, Status und Vortag trotzdem geschrieben', async () => {
  const u = umgebung(okZeile(10) + '\n');
  // Elternpfad ist eine Datei → mkdir scheitert wie bei fehlendem NAS-Mount.
  const blocker = path.join(u.dir, 'kein-nas');
  fs.writeFileSync(blocker, '');
  u.opts.berichtDir = path.join(blocker, 'Reports');
  await main(u.opts);
  const s = JSON.parse(fs.readFileSync(u.opts.statusDatei, 'utf8'));
  assert.equal(s.exit_code, 3);
  assert.match(s.fehler, /Bericht nicht schreibbar/);
  assert.equal(s.report_path, '');
  assert.equal(s.pruefungen.P1.anzahl, 1);
  assert.ok(fs.existsSync(path.join(u.opts.stateDir, 'letzter-stand.json')));
  assert.ok(u.mails.some((m) => /Bericht nicht schreibbar/.test(m.text)));
});

test('main: unerwarteter Fehler beim Schreiben ergibt exit 1 statt keinem Status', async () => {
  const u = umgebung(okZeile(10) + '\n');
  const blocker = path.join(u.dir, 'state-ist-datei');
  fs.writeFileSync(blocker, '');
  u.opts.stateDir = blocker;
  await main(u.opts);
  const s = JSON.parse(fs.readFileSync(u.opts.statusDatei, 'utf8'));
  assert.equal(s.exit_code, 1);
  assert.ok(s.fehler);
  assert.equal(u.mails.length, 1);
});

test('main: fehlender Spiegel bei frischem Log ergibt exit 3', async () => {
  const u = umgebung(okZeile(10) + '\n');
  u.opts.spiegel = path.join(u.dir, 'gibt-es-nicht');
  await main(u.opts);
  const s = JSON.parse(fs.readFileSync(u.opts.statusDatei, 'utf8'));
  assert.equal(s.exit_code, 3);
  assert.match(s.fehler, /Spiegel nicht lesbar/);
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
