const { test } = require('node:test');
const assert = require('node:assert/strict');
const { pruefe, gruppiere, PRUEFUNGEN } = require('../lib/pruefungen');

const VORLAGE = {
  typen: new Set(['Notiz', 'Songtext']),
  status: new Set(['Entwurf', 'In Bearbeitung', 'Abgeschlossen', 'Archiviert']),
  tagsMin: 2,
  tagsMax: 6,
};
const TAGS = ['a', 'b'];
const n = (pfad, fm = { tags: TAGS }, extra = {}) => ({
  pfad, groesse: 10, gross: false, fm, fmFehler: null, body: 'Text', hash: pfad, ...extra,
});
const pfade = (eintraege) => eintraege.map((e) => e.pfad).sort();

test('P1 meldet die Fehlerart ohne Zeilen- und Spaltenangabe', () => {
  // Sonst wird jede Datei zu einer eigenen Gruppe im Bericht.
  const b = pruefe([
    n('K/x.md', null, { fmFehler: 'unknown escape sequence at line 7, column 43:' }),
    n('K/y.md', null, { fmFehler: 'unknown escape sequence at line 7, column 34:' }),
  ], VORLAGE);
  assert.deepEqual(b.P1.map((e) => e.detail), ['unknown escape sequence', 'unknown escape sequence']);
});

test('P3 meldet typ außerhalb der Vorlage mit Wert als detail', () => {
  const b = pruefe([
    n('a.md', { typ: 'Kreativität/Songwriting/Blogtexte', tags: TAGS }),
    n('b.md', { typ: 'Songtext', tags: TAGS }),
    n('c.md', { tags: TAGS }),
  ], VORLAGE);
  assert.deepEqual(b.P3, [{ pfad: 'a.md', detail: 'Kreativität/Songwriting/Blogtexte' }]);
});

test('P4 meldet status Offen', () => {
  const b = pruefe([n('a.md', { status: 'Offen', tags: TAGS }), n('b.md', { status: 'Entwurf', tags: TAGS })], VORLAGE);
  assert.deepEqual(b.P4, [{ pfad: 'a.md', detail: 'Offen' }]);
});

test('P5: tags als String, 1 Tag, 7 Tags und fehlend', () => {
  const b = pruefe([
    n('string.md', { tags: 'Musik' }),
    n('eins.md', { tags: ['a'] }),
    n('sieben.md', { tags: ['1', '2', '3', '4', '5', '6', '7'] }),
    n('fehlt.md', {}),
    n('zwei.md', { tags: ['a', 'b'] }),
    n('sechs.md', { tags: ['1', '2', '3', '4', '5', '6'] }),
  ], VORLAGE);
  assert.deepEqual(pfade(b.P5), ['eins.md', 'fehlt.md', 'sieben.md', 'string.md']);
});

test('P6 löst Alias, Abschnitt, Einbettung und Ordnerpfad auf', () => {
  const quelle = n('Quelle.md', undefined, {
    body: '[[Ziel|x]] [[Ziel#h]] ![[Ziel]] [[Ordner/Ziel]] [[bild.png]] [[ziel]]',
  });
  const b = pruefe([quelle, n('Ordner/Ziel.md')], VORLAGE);
  assert.deepEqual(b.P6_echt, []);
  assert.deepEqual(b.P6_import, []);
});

test('P6 trennt echte tote Links von Import-Resten', () => {
  const quelle = n('Quelle.md', undefined, {
    body: '[[Gibtsnicht]] [[mailto:a@b.de]] [[http://x.de]] [[Bearbeiten]] [[[Bearbeiten]]',
  });
  const b = pruefe([quelle], VORLAGE);
  assert.deepEqual(b.P6_echt, [{ pfad: 'Quelle.md', detail: 'Gibtsnicht' }]);
  assert.equal(b.P6_import.length, 4);
});

test('P7 trennt inhaltsgleich und nur namensgleich', () => {
  const b = pruefe([
    n('A/Brief.md', undefined, { hash: 'h1' }),
    n('B/Brief.md', undefined, { hash: 'h1' }),
    n('A/Lied.md', undefined, { hash: 'h2' }),
    n('B/Lied.md', undefined, { hash: 'h3' }),
  ], VORLAGE);
  assert.deepEqual(pfade(b.P7_gleich), ['A/Brief.md', 'B/Brief.md']);
  assert.deepEqual(pfade(b.P7_name), ['A/Lied.md', 'B/Lied.md']);
  assert.equal(b.P7_name[0].detail, 'lied');
});

test('P8: gross, leerer body und Datei in der Wurzel', () => {
  const b = pruefe([
    n('E/gross.md', null, { gross: true, body: '', hash: null }),
    n('E/leer.md', undefined, { body: '  \n' }),
    n('_status.md'),
  ], VORLAGE);
  assert.deepEqual(pfade(b.P8), ['E/gross.md', 'E/leer.md', '_status.md']);
});

test('gruppiere zählt nach detail, absteigend, höchstens 10 Beispiele', () => {
  const eintraege = [
    ...Array.from({ length: 12 }, (_, i) => ({ pfad: `x${i}.md`, detail: 'Chat' })),
    { pfad: 'y.md', detail: 'Analysen' },
  ];
  const g = gruppiere(eintraege);
  assert.deepEqual(g.map((x) => [x.detail, x.anzahl]), [['Chat', 12], ['Analysen', 1]]);
  assert.equal(g[0].beispiele.length, 10);
});

test('PRUEFUNGEN beschreibt jede Prüfung mit Stufe und Quelle', () => {
  for (const k of ['P1', 'P2', 'P3', 'P4', 'P5', 'P6_echt', 'P6_import', 'P7_gleich', 'P7_name', 'P8']) {
    assert.ok(PRUEFUNGEN[k], k);
    assert.ok(['hoch', 'mittel', 'niedrig'].includes(PRUEFUNGEN[k].stufe), k);
    assert.ok(PRUEFUNGEN[k].quelle.length > 0, k);
  }
  assert.equal(PRUEFUNGEN.P1.stufe, 'hoch');
  assert.equal(PRUEFUNGEN.P2.stufe, 'hoch');
  assert.equal(PRUEFUNGEN.P6_echt.stufe, 'mittel');
  assert.equal(PRUEFUNGEN.P6_import.stufe, 'niedrig');
});
