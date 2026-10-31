const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const matter = require('gray-matter');
const { baueStatus, baueBericht, schreibeListen } = require('../lib/ausgabe');
const { pruefe, PRUEFUNGEN } = require('../lib/pruefungen');
const { ladeVorlage } = require('../lib/lesen');

const leer = () => ({ P1: [], P2: [], P3: [], P4: [], P5: [], P6_echt: [], P6_import: [], P7_gleich: [], P7_name: [], P8: [] });
const eintraege = (k, detail = 'x') => Array.from({ length: k }, (_, i) => ({ pfad: `N/${detail}${i}.md`, detail }));
const ZEIT = new Date('2026-11-01T00:45:12.345Z');
const status = (befunde, vorher = null) =>
  baueStatus({ befunde, vorher, notizenGesamt: 100, exitCode: 0, reportPath: '/r.md', zeit: ZEIT });

test('erster Lauf hat delta_vortag null und neu_hoch 0', () => {
  const b = leer();
  b.P1 = eintraege(6);
  const s = status(b);
  assert.equal(s.timestamp, '2026-11-01T00:45:12Z');
  assert.deepEqual(s.pruefungen.P1, { anzahl: 6, delta_vortag: null, stufe: 'hoch' });
  assert.equal(s.neu_hoch, 0);
  assert.equal(s.notizen_gesamt, 100);
  assert.equal(s.report_path, '/r.md');
});

test('Delta und neu_hoch zählen nur steigende hoch-Befunde', () => {
  const vorher = status(Object.assign(leer(), { P1: eintraege(6), P3: eintraege(10) }));
  const s = status(Object.assign(leer(), { P1: eintraege(8), P3: eintraege(12) }), vorher);
  assert.equal(s.pruefungen.P1.delta_vortag, 2);
  assert.equal(s.pruefungen.P3.delta_vortag, 2);
  assert.equal(s.neu_hoch, 2);
});

test('P2 null bleibt null, ohne Absturz', () => {
  const vorher = status(Object.assign(leer(), { P2: eintraege(3) }));
  const s = status(Object.assign(leer(), { P2: null }), vorher);
  assert.deepEqual(s.pruefungen.P2, { anzahl: null, delta_vortag: null, stufe: 'hoch' });
  assert.equal(s.neu_hoch, 0);
});

test('Bericht nennt Änderungen zuerst und je Prüfung die Quelle', () => {
  const b = Object.assign(leer(), { P1: eintraege(12, 'escape') });
  const md = baueBericht(status(b), b, '2026-11-01');
  const ueberschriften = md.match(/^## .+$/gm);
  assert.equal(ueberschriften[0], '## Änderungen zum Vortag');
  const p1 = md.slice(md.indexOf(PRUEFUNGEN.P1.titel));
  assert.ok(p1.includes(PRUEFUNGEN.P1.quelle));
  assert.equal((md.match(/N\/escape\d+\.md/g) || []).length, 10);
});

test('Bericht-Frontmatter besteht P3 und P5', () => {
  const md = baueBericht(status(leer()), leer(), '2026-11-01');
  const p = matter(md, {});
  const notiz = { pfad: 'Paperclip/_Meta/x.md', groesse: 1, gross: false, fm: p.data, fmFehler: null, body: p.content, hash: 'h' };
  const vorlage = ladeVorlage(path.join(__dirname, 'fixtures', 'vorlage.yaml'));
  const b = pruefe([notiz], vorlage);
  assert.deepEqual(b.P3, []);
  assert.deepEqual(b.P5, []);
});

test('schreibeListen legt je Prüfung eine sortierte Datei an', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpc-'));
  const b = Object.assign(leer(), { P1: [{ pfad: 'b.md', detail: 'y' }, { pfad: 'a.md', detail: 'x' }], P2: null });
  schreibeListen(b, dir);
  assert.equal(fs.readFileSync(path.join(dir, 'P1.txt'), 'utf8'), 'a.md\tx\nb.md\ty\n');
  assert.ok(fs.existsSync(path.join(dir, 'P3.txt')));
  assert.ok(!fs.existsSync(path.join(dir, 'P2.txt')));
});
