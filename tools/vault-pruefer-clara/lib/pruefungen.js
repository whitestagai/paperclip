// Strukturprüfungen P1, P3–P8 über die geladenen Notizen. P2 (Index-Abgleich)
// steht in index-abgleich.js, weil es die Datenbank braucht.
//
// Jede Prüfung liefert Einträge { pfad, detail }. Die Quelle nennt das Werkzeug,
// das den Befund vermutlich erzeugt — repariert wird dort, nicht im Vault.

const PRUEFUNGEN = {
  P1: { titel: 'Frontmatter vom Index nicht lesbar', stufe: 'hoch', quelle: 'n8n Clara-Kontakte/Termine-Workflow (schreibt \\, und bricht Zeilen falsch)' },
  P2: { titel: 'Notiz fehlt im Brain-Index oder hat keine Chunks', stufe: 'hoch', quelle: 'Brain-Indexer com.whitestag.brain-indexer-clara' },
  P3: { titel: 'typ nicht in der Vorlage', stufe: 'mittel', quelle: 'Dokumenten-Import (typ = Ordnerpfad) / ChatGPT-Import (typ: Chat)' },
  P4: { titel: 'status nicht in der Vorlage', stufe: 'mittel', quelle: 'Hand-Notizen' },
  P5: { titel: 'tags fehlen oder außerhalb 2–6', stufe: 'niedrig', quelle: 'gemischt (Importe, Hand-Notizen)' },
  P6_echt: { titel: 'Wikilink ohne Ziel', stufe: 'mittel', quelle: 'Hand-Notizen, umbenannte oder gelöschte Ziele' },
  P6_import: { titel: 'Wikilink-Rest aus Import (http, mailto, Bearbeiten)', stufe: 'niedrig', quelle: 'Word-/Web-Import' },
  P7_gleich: { titel: 'Gleicher Name, gleicher Inhalt in mehreren Ordnern', stufe: 'niedrig', quelle: 'Kopien zwischen Ordnern' },
  P7_name: { titel: 'Gleicher Name, anderer Inhalt in mehreren Ordnern', stufe: 'niedrig', quelle: 'Fassungen oder Kopien zwischen Ordnern' },
  P8: { titel: 'Notiz über 2 MB, leer oder in der Wurzel', stufe: 'niedrig', quelle: 'E-Mail-Import (eingebettete Anhänge) / Hand' },
};

const LINK = /!?\[\[([^\]|#^]+)/g;
const ANHANG = /\.(png|jpe?g|gif|webp|svg|pdf|mp3|wav|m4a|canvas)$/i;
const istImportRest = (ziel) => /^(http|mailto:|\[)/i.test(ziel) || ziel === 'Bearbeiten';

const basisname = (pfad) => pfad.split('/').pop().replace(/\.md$/, '').toLowerCase();

function pruefe(notizen, vorlage) {
  const b = { P1: [], P3: [], P4: [], P5: [], P6_echt: [], P6_import: [], P7_gleich: [], P7_name: [], P8: [] };
  const namen = new Map();
  const relPfade = new Set();
  for (const n of notizen) {
    const name = basisname(n.pfad);
    if (!namen.has(name)) namen.set(name, []);
    namen.get(name).push(n);
    relPfade.add(n.pfad.replace(/\.md$/, '').toLowerCase());
  }
  const existiert = (ziel) => {
    const z = ziel.trim().replace(/\.md$/i, '').toLowerCase();
    return relPfade.has(z) || namen.has(z.split('/').pop());
  };

  for (const n of notizen) {
    if (n.fmFehler) b.P1.push({ pfad: n.pfad, detail: n.fmFehler.replace(/ at line \d+.*$/, '').replace(/[;:]\s*$/, '') });
    if (n.fm) {
      const { typ, status, tags } = n.fm;
      if (typ != null && !vorlage.typen.has(String(typ))) b.P3.push({ pfad: n.pfad, detail: String(typ) });
      if (status != null && !vorlage.status.has(String(status))) b.P4.push({ pfad: n.pfad, detail: String(status) });
      if (!Array.isArray(tags)) b.P5.push({ pfad: n.pfad, detail: tags == null ? 'fehlt' : 'keine Liste' });
      else if (tags.length < vorlage.tagsMin || tags.length > vorlage.tagsMax) b.P5.push({ pfad: n.pfad, detail: `${tags.length} Tags` });
    }
    for (const [, roh] of n.body.matchAll(LINK)) {
      const ziel = roh.trim();
      if (istImportRest(ziel)) b.P6_import.push({ pfad: n.pfad, detail: ziel });
      else if (!ANHANG.test(ziel) && !existiert(ziel)) b.P6_echt.push({ pfad: n.pfad, detail: ziel });
    }
    if (n.gross) b.P8.push({ pfad: n.pfad, detail: 'über 2 MB' });
    else if (n.body.trim() === '') b.P8.push({ pfad: n.pfad, detail: 'leer' });
    if (!n.pfad.includes('/')) b.P8.push({ pfad: n.pfad, detail: 'in der Wurzel' });
  }

  for (const [name, gruppe] of namen) {
    if (gruppe.length < 2) continue;
    const gleich = gruppe.every((n) => n.hash !== null && n.hash === gruppe[0].hash);
    for (const n of gruppe) (gleich ? b.P7_gleich : b.P7_name).push({ pfad: n.pfad, detail: name });
  }
  return b;
}

function gruppiere(eintraege) {
  const g = new Map();
  for (const e of eintraege) {
    if (!g.has(e.detail)) g.set(e.detail, { detail: e.detail, anzahl: 0, beispiele: [] });
    const x = g.get(e.detail);
    x.anzahl++;
    if (x.beispiele.length < 10) x.beispiele.push(e.pfad);
  }
  return [...g.values()].sort((a, b) => b.anzahl - a.anzahl);
}

module.exports = { pruefe, gruppiere, PRUEFUNGEN };
