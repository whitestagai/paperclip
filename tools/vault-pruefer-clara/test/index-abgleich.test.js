const { test } = require('node:test');
const assert = require('node:assert/strict');
const { vergleicheIndex } = require('../lib/index-abgleich');

const n = (pfad, extra = {}) => ({
  pfad, groesse: 10, gross: false, fm: {}, fmFehler: null, body: 'Text', hash: 'h', ...extra,
});

test('fehlt im Index und keine Chunks werden erkannt', () => {
  const e = vergleicheIndex(
    [n('A/fehlt.md'), n('A/leer-im-index.md'), n('A/ok.md')],
    [{ path: 'A/leer-im-index.md', chunks: 0 }, { path: 'A/ok.md', chunks: 3 }],
  );
  assert.deepEqual(e, [
    { pfad: 'A/fehlt.md', detail: 'fehlt im Index' },
    { pfad: 'A/leer-im-index.md', detail: 'keine Chunks' },
  ]);
});

test('NFD-Pfad im Index passt zu NFC-Notiz', () => {
  const e = vergleicheIndex(
    [n('Kontakte/Müller.md'.normalize('NFC'))],
    [{ path: 'Kontakte/Müller.md'.normalize('NFD'), chunks: 2 }],
  );
  assert.deepEqual(e, []);
});

test('Ausschlüsse, gross, leer und fmFehler werden nicht gemeldet', () => {
  const e = vergleicheIndex([
    n('Analysen/Link-Erkennung-Shadow/2026-05-29.md'),
    n('Analysen/LLM-Nutzung/2026-09-13.md'),
    n('attachments/x.md'),
    n('E/gross.md', { gross: true, body: '' }),
    n('E/leer.md', { body: ' \n' }),
    n('K/kaputt.md', { fm: null, fmFehler: 'escape' }),
    n('Analysen/Meta.md'),
  ], []);
  assert.deepEqual(e, [{ pfad: 'Analysen/Meta.md', detail: 'fehlt im Index' }]);
});
