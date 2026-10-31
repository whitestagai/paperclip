// P2: Abgleich der Notizen mit dem Brain-Index (paperclip_brain_clara).
//
// Ausschlüsse und Größengrenze müssen exakt dem Indexer entsprechen
// (packages/brain/src/indexer/watcher.ts), sonst meldet P2 Notizen, die der
// Indexer bewusst nie aufnimmt.
const postgres = require('postgres');

const AUSGESCHLOSSEN = new Set([
  'attachments',
  '.obsidian',
  '.trash',
  'Analysen/Link-Erkennung',
  'Analysen/Link-Erkennung-Shadow',
  'Analysen/LLM-Nutzung',
]);

function ausgeschlossen(pfad) {
  const teile = pfad.split('/');
  for (let i = 1; i < teile.length; i++) {
    if (AUSGESCHLOSSEN.has(teile.slice(0, i).join('/'))) return true;
  }
  return false;
}

function vergleicheIndex(notizen, index) {
  const chunks = new Map(index.map((r) => [r.path.normalize('NFC'), r.chunks]));
  const eintraege = [];
  for (const n of notizen) {
    // Ungültiges Frontmatter steht schon in P1; Große und Leere nimmt der Indexer nie auf.
    if (n.gross || n.fmFehler || n.body.trim() === '' || ausgeschlossen(n.pfad)) continue;
    const pfad = n.pfad.normalize('NFC');
    if (!chunks.has(pfad)) eintraege.push({ pfad: n.pfad, detail: 'fehlt im Index' });
    else if (chunks.get(pfad) === 0) eintraege.push({ pfad: n.pfad, detail: 'keine Chunks' });
  }
  return eintraege;
}

async function ladeIndex(url) {
  const sql = postgres(url, { max: 1, connect_timeout: 10, onnotice: () => {} });
  try {
    return await sql`
      select n.path, count(c.id)::int as chunks
      from brain.notes n left join brain.chunks c on c.note_id = n.id
      group by n.path`;
  } finally {
    await sql.end({ timeout: 5 });
  }
}

module.exports = { vergleicheIndex, ladeIndex };
