const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { ladeVorlage, ladeNotizen } = require('../lib/lesen');

const FIX = path.join(__dirname, 'fixtures');
const notiz = (liste, pfad) => liste.find((n) => n.pfad === pfad.normalize('NFC'));

test('ladeVorlage liest Typen und Status', () => {
  const v = ladeVorlage(path.join(FIX, 'vorlage.yaml'));
  assert.ok(v.typen.has('Songtext'));
  assert.ok(!v.typen.has('Chat'));
  assert.ok(v.status.has('In Bearbeitung'));
  assert.equal(v.status.size, 4);
  assert.equal(v.tagsMin, 2);
  assert.equal(v.tagsMax, 6);
});

test('ladeNotizen liefert NFC-Pfade mit Schrägstrich', () => {
  // Zur Laufzeit angelegt: git auf dem Mac würde einen NFD-Namen im Fixture
  // beim Einchecken zu NFC zusammensetzen, und der Test prüfte nichts mehr.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpc-'));
  fs.mkdirSync(path.join(dir, 'Kontakte'));
  fs.writeFileSync(path.join(dir, 'Kontakte', 'Müller'.normalize('NFD') + '.md'), '---\ntitle: Müller\n---\nText\n');
  const n = notiz(ladeNotizen(dir), 'Kontakte/Müller.md');
  assert.ok(n, 'Müller.md nicht unter NFC-Pfad gefunden');
  assert.equal(n.fm.title, 'Müller');
});

test('ungültiges YAML landet in fmFehler', () => {
  const n = notiz(ladeNotizen(path.join(FIX, 'vault')), 'Kontakte/Kaputt.md');
  assert.equal(n.fm, null);
  assert.match(n.fmFehler, /escape/);
});

test('Frontmatter als Liste stürzt nicht ab', () => {
  const n = notiz(ladeNotizen(path.join(FIX, 'vault')), 'Liste/Als-Liste.md');
  assert.equal(n.fmFehler, null);
  assert.deepEqual(n.fm, {});
});

test('hash hängt nur am Inhalt, nicht am Frontmatter', () => {
  // Kopien zwischen Ordnern unterscheiden sich fast immer in erstellt/quelle.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpc-'));
  fs.writeFileSync(path.join(dir, 'a.md'), '---\nerstellt: 2026-05-31\n---\nGleicher Text\n');
  fs.writeFileSync(path.join(dir, 'b.md'), '---\nerstellt: 2026-06-02\n---\nGleicher Text\n');
  const [a, b] = ladeNotizen(dir);
  assert.equal(a.hash, b.hash);
});

test('Dateien über 2 MB werden nicht gelesen', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpc-'));
  fs.writeFileSync(path.join(dir, 'gross.md'), 'x'.repeat(2 * 1024 * 1024 + 1));
  const [n] = ladeNotizen(dir);
  assert.equal(n.gross, true);
  assert.equal(n.hash, null);
  assert.equal(n.body, '');
});
