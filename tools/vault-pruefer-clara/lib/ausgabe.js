// Status-Datei (für den Agenten), Bericht (für Walter und Clara) und
// vollständige Listen (Grundlage jeder späteren Korrektur „nur nach Liste").
const fs = require('fs');
const path = require('path');
const { PRUEFUNGEN, gruppiere } = require('./pruefungen');

const SCHLUESSEL = Object.keys(PRUEFUNGEN);
const MAX_GRUPPEN = 15;

function baueStatus({ befunde, vorher, notizenGesamt, exitCode, reportPath, zeit }) {
  const pruefungen = {};
  let neuHoch = 0;
  for (const k of SCHLUESSEL) {
    const anzahl = befunde[k] == null ? null : befunde[k].length;
    const alt = vorher?.pruefungen?.[k]?.anzahl;
    const delta = anzahl == null || alt == null ? null : anzahl - alt;
    const { stufe } = PRUEFUNGEN[k];
    if (stufe === 'hoch' && delta > 0) neuHoch += delta;
    pruefungen[k] = { anzahl, delta_vortag: delta, stufe };
  }
  return {
    timestamp: zeit.toISOString().replace(/\.\d{3}Z$/, 'Z'),
    exit_code: exitCode,
    notizen_gesamt: notizenGesamt,
    pruefungen,
    neu_hoch: neuHoch,
    report_path: reportPath,
  };
}

const zahl = (x) => (x == null ? '–' : String(x));
const delta = (x) => (x == null ? '–' : x > 0 ? `+${x}` : String(x));

function baueBericht(status, befunde, datum) {
  const z = [
    '---',
    `title: "Vault-Prüfung Clara ${datum}"`,
    `datum: ${datum}`,
    'typ: Notiz',
    'status: Abgeschlossen',
    'tags:',
    '  - Vault-Pflege',
    '  - Bericht',
    'quelle: "de.whitestag.vault-pruefer-clara"',
    '---',
    '',
    `# Vault-Prüfung Clara ${datum}`,
    '',
    `Lauf ${status.timestamp} · exit_code ${status.exit_code} · ${status.notizen_gesamt} Notizen`,
    '',
    '## Änderungen zum Vortag',
    '',
  ];
  const p = status.pruefungen;
  const ersterLauf = SCHLUESSEL.every((k) => p[k].delta_vortag == null);
  const geaendert = SCHLUESSEL.filter((k) => p[k].delta_vortag);
  if (ersterLauf) z.push('Erster Lauf — dieser Stand ist die Baseline.');
  else if (geaendert.length === 0) z.push('Keine Änderungen.');
  else for (const k of geaendert) z.push(`- **${PRUEFUNGEN[k].titel}** (${k}, ${p[k].stufe}): ${delta(p[k].delta_vortag)} → ${zahl(p[k].anzahl)}`);

  z.push('', '## Übersicht', '', '| Prüfung | Stufe | Anzahl | Δ Vortag |', '|---|---|---:|---:|');
  for (const k of SCHLUESSEL) z.push(`| ${k} ${PRUEFUNGEN[k].titel} | ${p[k].stufe} | ${zahl(p[k].anzahl)} | ${delta(p[k].delta_vortag)} |`);

  for (const k of SCHLUESSEL) {
    if (!befunde[k] || befunde[k].length === 0) continue;
    const gruppen = gruppiere(befunde[k]);
    z.push('', `## ${k} ${PRUEFUNGEN[k].titel}`, '', `Quelle: ${PRUEFUNGEN[k].quelle}`, '');
    for (const g of gruppen.slice(0, MAX_GRUPPEN)) {
      z.push(`- **${g.detail}** — ${g.anzahl}`);
      for (const b of g.beispiele) z.push(`  - \`${b}\``);
    }
    if (gruppen.length > MAX_GRUPPEN) z.push(`- … ${gruppen.length - MAX_GRUPPEN} weitere Gruppen in der vollständigen Liste`);
  }
  return z.join('\n') + '\n';
}

function schreibeListen(befunde, verzeichnis) {
  fs.mkdirSync(verzeichnis, { recursive: true });
  for (const k of SCHLUESSEL) {
    if (befunde[k] == null) continue;
    const zeilen = befunde[k].map((e) => `${e.pfad}\t${e.detail}`).sort();
    fs.writeFileSync(path.join(verzeichnis, `${k}.txt`), zeilen.length ? zeilen.join('\n') + '\n' : '');
  }
}

module.exports = { baueStatus, baueBericht, schreibeListen };
