// Liest die Frontmatter-Vorlage und alle Notizen eines Vaults.
//
// Frontmatter wird mit gray-matter geparst, also mit derselben Bibliothek wie
// der Brain-Indexer: „gültig" heißt hier genau „vom Index lesbar".
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const matter = require('gray-matter');

const MAX_GROESSE = 2 * 1024 * 1024; // wie MAX_FILE_SIZE im Brain-Indexer

function ladeVorlage(pfad) {
  const roh = fs.readFileSync(pfad, 'utf8');
  const yaml = matter.engines.yaml.parse(roh);
  // Die erlaubten Status-Werte stehen nur im Kommentar der basis.status-Zeile.
  const m = roh.match(/^\s*status:\s*#\s*(.+)$/m);
  const status = new Set(m ? m[1].split('|').map((s) => s.trim()).filter(Boolean) : []);
  return { typen: new Set(Object.keys(yaml.typen || {})), status, tagsMin: 2, tagsMax: 6 };
}

function* mdDateien(wurzel, rel = '') {
  for (const e of fs.readdirSync(path.join(wurzel, rel), { withFileTypes: true })) {
    if (e.name.startsWith('.')) continue;
    const r = rel ? rel + '/' + e.name : e.name;
    if (e.isDirectory()) yield* mdDateien(wurzel, r);
    else if (e.isFile() && e.name.endsWith('.md')) yield r;
  }
}

function ladeNotizen(wurzel) {
  const notizen = [];
  for (const rel of mdDateien(wurzel)) {
    const abs = path.join(wurzel, rel);
    const groesse = fs.statSync(abs).size;
    const n = { pfad: rel.normalize('NFC'), groesse, gross: groesse > MAX_GROESSE, fm: null, fmFehler: null, body: '', hash: null };
    if (!n.gross) {
      const roh = fs.readFileSync(abs, 'utf8');
      try {
        // Leeres Optionsobjekt: gray-matter cacht sonst nach Inhalt und
        // liefert für gleichen Text dasselbe Objekt zurück.
        const p = matter(roh, {});
        n.fm = p.data && typeof p.data === 'object' && !Array.isArray(p.data) ? p.data : {};
        n.body = p.content;
      } catch (e) {
        n.fmFehler = String(e.message).split('\n')[0];
        n.body = roh;
      }
      // Nur der Text zählt: Kopien unterscheiden sich fast immer im Frontmatter.
      n.hash = crypto.createHash('sha256').update(n.body.trim()).digest('hex');
    }
    notizen.push(n);
  }
  return notizen;
}

module.exports = { ladeVorlage, ladeNotizen, MAX_GROESSE };
