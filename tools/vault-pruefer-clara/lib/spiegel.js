// Ist der lokale Spiegel frisch genug, um über den Vault zu urteilen?
//
// sync-clara-mirror.js schreibt alle 15 Minuten eine Zeile
// „YYYY-MM-DD HH:MM:SS  OK (node): … .md gespiegelt." in Berliner Zeit.
// Maßgeblich ist das letzte OK — ein späterer ABBRUCH lässt den Spiegel
// unverändert, er ist dann so alt wie dieses OK.
const OK_ZEILE = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})  OK /;

// Berliner Wandzeit → Date, unabhängig von der Zeitzone des Rechners.
function ausBerlin(j, mo, t, h, mi, s) {
  const alsUtc = Date.UTC(j, mo - 1, t, h, mi, s);
  const wand = new Date(alsUtc).toLocaleString('sv-SE', { timeZone: 'Europe/Berlin' });
  const [d, z] = wand.split(' ');
  const [wj, wmo, wt] = d.split('-').map(Number);
  const [wh, wmi, ws] = z.split(':').map(Number);
  const versatz = Date.UTC(wj, wmo - 1, wt, wh, wmi, ws) - alsUtc;
  return new Date(alsUtc - versatz);
}

function spiegelAktuell(logText, jetzt, maxMinuten = 60) {
  const zeilen = String(logText).split('\n');
  for (let i = zeilen.length - 1; i >= 0; i--) {
    const m = zeilen[i].match(OK_ZEILE);
    if (!m) continue;
    const alter = Math.round((jetzt - ausBerlin(...m.slice(1).map(Number))) / 60000);
    return alter <= maxMinuten
      ? { ok: true, grund: `letzter Sync vor ${alter} min` }
      : { ok: false, grund: `letzter erfolgreicher Sync vor ${alter} min (Grenze ${maxMinuten} min)` };
  }
  return { ok: false, grund: 'kein erfolgreicher Sync im Log' };
}

module.exports = { spiegelAktuell };
