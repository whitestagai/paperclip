// scripts/kurs-check.ts
import { readFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

// seed/parse-content.ts
var LABELS = [
  "Lernziel",
  "Inhalt",
  "Praxisaufgabe",
  "Prompt-\xDCbung",
  "Feedback-Fokus",
  "Wissens-Check"
];
var escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function markerRegex(label) {
  const l = escape(label);
  return new RegExp(`\\*\\*${l}:\\*\\*|^#{2,4}[ \\t]*${l}(?![\\w\xC4\xD6\xDC\xE4\xF6\xFC\xDF-])[^\\n]*$`, "gm");
}
var STOPPERS = {
  "Feedback-Fokus": ["Abschlusstest"],
  "Wissens-Check": ["Quellen", "Abschlusstest"]
};
function cutSegment(text, label) {
  const alts = ["\\n---", ...(STOPPERS[label] ?? []).map((s) => `\\*\\*${escape(s)}`)];
  const stop = text.search(new RegExp(alts.join("|")));
  return (stop === -1 ? text : text.slice(0, stop)).trim();
}
function splitSections(body) {
  const found = [];
  let pos = 0;
  for (const label of LABELS) {
    const re = markerRegex(label);
    re.lastIndex = pos;
    const m = re.exec(body);
    if (!m) continue;
    found.push({ label, start: m.index, end: m.index + m[0].length });
    pos = m.index + m[0].length;
  }
  const out = {};
  found.forEach((f, i) => {
    const next = found[i + 1]?.start ?? body.length;
    out[f.label] = cutSegment(body.slice(f.end, next), f.label);
  });
  return out;
}
function parseCheck(raw) {
  if (!raw) return { question: null, answer: null };
  const details = raw.match(/<details>([\s\S]*?)<\/details>/);
  if (details) {
    const question = raw.slice(0, details.index).trim();
    const answer = details[1].replace(/^[ \t]*<summary>.*$/m, "").replace(/<\/?summary>/g, "").trim();
    return { question: question || null, answer: answer || null };
  }
  const parts = raw.split(/\s*—\s*|\s+-\s+/);
  if (parts.length >= 2) {
    const question = parts[0].trim();
    const answer = parts.slice(1).join(" \u2014 ").trim().replace(/^\*(.+)\*$/, "$1").trim();
    return { question, answer };
  }
  return { question: raw, answer: null };
}
function extractPrivacySection(tail) {
  const m = tail.match(/(?:^|\n)## (Datenschutz[^\n]*)\n([\s\S]*?)(?=\n## |$)/);
  if (!m) return null;
  const body = m[2].replace(/\n-{3,}\s*$/, "").trim();
  return body ? `${m[1].trim()}

${body}` : null;
}
function parseLessons(md) {
  const blocks = md.split(/\n## Lektion (\d+) — (.+)\n/);
  const out = [];
  for (let i = 1; i < blocks.length; i += 3) {
    const day = parseInt(blocks[i], 10);
    if (Number.isNaN(day)) continue;
    const title = blocks[i + 1]?.trim() ?? "";
    const rawBody = blocks[i + 2] ?? "";
    const h2 = rawBody.search(/\n## /);
    const body = h2 === -1 ? rawBody : rawBody.slice(0, h2);
    const s = splitSections(body);
    let goal = s.Lernziel ?? "";
    let content = s.Inhalt ?? "";
    if (s.Inhalt === void 0) {
      const para = goal.search(/\n\s*\n/);
      if (para !== -1) {
        content = goal.slice(para).trim();
        goal = goal.slice(0, para).trim();
      }
    }
    const { question, answer } = parseCheck(s["Wissens-Check"]);
    out.push({
      day_index: day,
      title,
      goal,
      content,
      practice_task: s.Praxisaufgabe ?? "",
      prompt_exercise: s["Prompt-\xDCbung"] ?? "",
      prompt_feedback_focus: s["Feedback-Fokus"] ?? "",
      check_question: question,
      check_answer: answer
    });
  }
  if (out.length > 0) {
    const privacy = extractPrivacySection(blocks[blocks.length - 1] ?? "");
    if (privacy) {
      const last = out[out.length - 1];
      last.content = last.content ? `${last.content}

${privacy}` : privacy;
    }
  }
  return out;
}

// src/import/validate-course.ts
var LONG_DESCRIPTION_MIN = 1200;
var LONG_DESCRIPTION_MAX = 3e3;
var SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
var GROUPS = ["grundlagen", "aufbau", "aufgabe", "branche"];
var LEVELS = ["einsteiger", "fortgeschritten"];
var CATEGORY_RULES = {
  grundlagen: { test: (s) => s === "Grundlagen", hint: "\u201EGrundlagen\u201C" },
  aufbau: { test: (s) => /^Aufbau · Stufe \d+$/.test(s), hint: "\u201EAufbau \xB7 Stufe N\u201C" },
  aufgabe: { test: (s) => s === "Nach Aufgabe", hint: "\u201ENach Aufgabe\u201C" },
  branche: { test: (s) => /^Branche · .+$/.test(s), hint: "\u201EBranche \xB7 \u2026\u201C" }
};
function stripValue(raw) {
  const v = raw.trim();
  const q = v.match(/^(["'])(.*?)\1(?:\s+#.*)?$/);
  if (q) return q[2];
  return v.replace(/\s+#.*$/, "").trim();
}
function parseFrontmatter(md) {
  const m = md.replace(/\r\n?/g, "\n").match(/^---[ \t]*\n([\s\S]*?)\n---[ \t]*(?:\n|$)/);
  const out = {};
  if (!m) return out;
  for (const line of m[1].split("\n")) {
    const kv = line.match(/^([A-Za-z0-9_]+):(.*)$/);
    if (kv) out[kv[1]] = stripValue(kv[2]);
  }
  return out;
}
function validateCourse(slug, md) {
  const text = md.replace(/\r\n?/g, "\n");
  const fm = parseFrontmatter(text);
  const problems = [];
  if (!SLUG_PATTERN.test(slug)) {
    problems.push("Der slug ist ung\xFCltig: erlaubt sind Kleinbuchstaben, Ziffern und einzelne Bindestriche.");
  }
  if (!fm.kurs_id) problems.push("Das Frontmatter-Feld kurs_id fehlt.");
  else if (fm.kurs_id !== slug) {
    problems.push(`Das Frontmatter-Feld kurs_id (\u201E${fm.kurs_id}\u201C) stimmt nicht mit dem slug (\u201E${slug}\u201C) \xFCberein.`);
  }
  if (!fm.title) problems.push("Das Frontmatter-Feld title fehlt.");
  const group = fm.kurs_gruppe;
  const groupOk = !!group && GROUPS.includes(group);
  if (!fm.kurs_gruppe) problems.push("Das Frontmatter-Feld kurs_gruppe fehlt.");
  else if (!groupOk) {
    problems.push(`Das Frontmatter-Feld kurs_gruppe (\u201E${fm.kurs_gruppe}\u201C) muss grundlagen, aufbau, aufgabe oder branche sein.`);
  }
  if (!fm.kurs_kategorie) problems.push("Das Frontmatter-Feld kurs_kategorie fehlt.");
  else if (groupOk && !CATEGORY_RULES[group].test(fm.kurs_kategorie)) {
    problems.push(
      `Das Frontmatter-Feld kurs_kategorie (\u201E${fm.kurs_kategorie}\u201C) passt nicht zur Gruppe ${group}; erwartet wird ${CATEGORY_RULES[group].hint}.`
    );
  }
  const level = fm.kurs_niveau;
  if (!fm.kurs_niveau) problems.push("Das Frontmatter-Feld kurs_niveau fehlt.");
  else if (!LEVELS.includes(level)) {
    problems.push(`Das Frontmatter-Feld kurs_niveau (\u201E${fm.kurs_niveau}\u201C) muss einsteiger oder fortgeschritten sein.`);
  }
  for (const key of ["kurzbeschreibung", "kurzbeschreibung_sie"]) {
    const v = fm[key];
    if (!v) problems.push(`Das Frontmatter-Feld ${key} fehlt.`);
    else if (v.length > 160) {
      problems.push(`Das Frontmatter-Feld ${key} ist ${v.length} Zeichen lang, erlaubt sind h\xF6chstens 160.`);
    }
  }
  const long = { langbeschreibung: null, langbeschreibung_sie: null };
  for (const key of ["langbeschreibung", "langbeschreibung_sie"]) {
    const v = fm[key]?.replace(/\\n/g, "\n").trim();
    if (!v) continue;
    if (v.length < LONG_DESCRIPTION_MIN || v.length > LONG_DESCRIPTION_MAX) {
      problems.push(`Das Frontmatter-Feld ${key} ist ${v.length} Zeichen lang, erlaubt sind ${LONG_DESCRIPTION_MIN} bis ${LONG_DESCRIPTION_MAX}.`);
    }
    long[key] = v;
  }
  if (!fm.tool_stand_gelesen) problems.push("Das Frontmatter-Feld tool_stand_gelesen fehlt.");
  else if (!/^\d{4}-\d{2}-\d{2}$/.test(fm.tool_stand_gelesen)) {
    problems.push("Das Frontmatter-Feld tool_stand_gelesen muss ein Datum im Format JJJJ-MM-TT sein.");
  }
  const lessons = parseLessons(text);
  if (lessons.length === 0) {
    problems.push("Es wurde keine Lektion im Format \u201E## Lektion N \u2014 Titel\u201C gefunden.");
  } else {
    lessons.forEach((l, i) => {
      if (l.day_index !== i + 1) {
        problems.push(`Lektion ${l.day_index}: Die Nummerierung ist l\xFCckenhaft oder unsortiert, erwartet wurde Lektion ${i + 1}.`);
      }
    });
    for (const l of lessons) {
      const missing = [
        ["Titel", l.title],
        ["Lernziel", l.goal],
        ["Inhalt", l.content],
        ["Praxisaufgabe", l.practice_task],
        ["Prompt-\xDCbung", l.prompt_exercise],
        ["Feedback-Fokus", l.prompt_feedback_focus]
      ];
      for (const [name, v] of missing) {
        if (!v?.trim()) problems.push(`Lektion ${l.day_index}: ${name} fehlt oder ist leer.`);
      }
      if (!l.check_question?.trim() || !l.check_answer?.trim()) {
        problems.push(`Lektion ${l.day_index}: Der Wissens-Check braucht eine Frage und eine Antwort (in <details>).`);
      }
    }
  }
  if (problems.length > 0) return { ok: false, problems };
  return {
    ok: true,
    course: {
      slug,
      title: fm.title,
      courseGroup: group,
      categoryLabel: fm.kurs_kategorie,
      level,
      description: fm.kurzbeschreibung,
      descriptionSie: fm.kurzbeschreibung_sie,
      longDescription: long.langbeschreibung,
      longDescriptionSie: long.langbeschreibung_sie,
      lessons
    }
  };
}

// scripts/kurs-check.ts
var SPEC_FIELDS = [
  "title",
  "datum",
  "paperclip_issue_id",
  "paperclip_agent",
  "paperclip_company",
  "paperclip_status",
  "type",
  "tags",
  "zusammenfassung",
  "kurs_id",
  "is_free",
  "tool_stand_gelesen",
  "kurs_gruppe",
  "kurs_niveau",
  "kurs_kategorie",
  "kurzbeschreibung",
  "kurzbeschreibung_sie",
  "langbeschreibung",
  "langbeschreibung_sie"
];
var DATENSCHUTZ = "## Datenschutz \u2014 was du beachten musst";
function frontmatterLines(md) {
  const m = md.match(/^---[ \t]*\n([\s\S]*?)\n---[ \t]*(?:\n|$)/);
  return m ? m[1].split("\n") : null;
}
function checkCourse(slug, rawMd, opts = {}) {
  const md = rawMd.replace(/\r\n?/g, "\n");
  const fehler = [];
  const warnungen = [];
  const v = validateCourse(slug, md);
  if (!v.ok) fehler.push(...v.problems.map((p) => `[Import] ${p}`));
  const lines = frontmatterLines(md);
  if (!lines) {
    fehler.push("[Spec \xA7 8] Kein Frontmatter-Block (--- \u2026 ---) am Dateianfang.");
    return { fehler, warnungen };
  }
  const fields = [];
  const stray = [];
  lines.forEach((line, i) => {
    const kv = line.match(/^([A-Za-z0-9_]+):(.*)$/);
    if (kv) fields.push({ key: kv[1], val: kv[2].trim(), extra: 0 });
    else if (line.trim() && !line.trim().startsWith("#")) {
      if (fields.length) fields[fields.length - 1].extra++;
      else stray.push(i + 2);
    }
  });
  for (const ln of stray) fehler.push(`[Spec \xA7 8] Frontmatter-Zeile ${ln} ist keine \u201Efeld: wert\u201C-Zeile.`);
  for (const f of fields) {
    if (f.extra) {
      fehler.push(
        `[Spec \xA7 8] Feld ${f.key} geht \xFCber mehrere Zeilen. Der Import liest nur die erste Zeile. Den ganzen Wert in EINE Zeile schreiben, Abs\xE4tze als \\n\\n (Backslash-n), keine echten Zeilenumbr\xFCche.`
      );
      continue;
    }
    const val = f.val.replace(/\s+#[^"]*$/, "");
    if (val.startsWith('"') && !/^"[^"]*"$/.test(val)) {
      fehler.push(
        `[Spec \xA7 8] Feld ${f.key}: der Wert muss in "\u2026" stehen und darf innen keine geraden Anf\xFChrungszeichen " enthalten (typografisch \u201E\u2026\u201C verwenden).`
      );
    }
  }
  const fm = parseFrontmatter(md);
  for (const key of SPEC_FIELDS) {
    if (!fm[key]) fehler.push(`[Spec \xA7 8] Pflichtfeld ${key} fehlt oder ist leer.`);
  }
  if (fm.tags) {
    const tags = fm.tags.replace(/^\[|\]$/g, "").split(",").map((t) => t.trim().replace(/^["']|["']$/g, ""));
    if (tags[0] !== "paperclip" || tags[1] !== "whitestag-academy" || !tags.includes(slug)) {
      fehler.push(`[Spec \xA7 8] tags ist \u201E${fm.tags}\u201C, verlangt ist genau: [paperclip, whitestag-academy, ${slug}]`);
    }
  }
  if (fm.is_free && !["true", "false"].includes(fm.is_free)) {
    fehler.push(`[Spec \xA7 8] is_free ist \u201E${fm.is_free}\u201C, erlaubt sind true oder false.`);
  }
  if (fm.type && fm.type !== "deliverable") fehler.push(`[Spec \xA7 8] type ist \u201E${fm.type}\u201C, verlangt ist deliverable.`);
  if (fm.paperclip_company && fm.paperclip_company !== "whitestag") {
    fehler.push(`[Spec \xA7 8] paperclip_company ist \u201E${fm.paperclip_company}\u201C, verlangt ist whitestag.`);
  }
  if (fm.datum) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(fm.datum)) fehler.push("[Spec \xA7 8] datum muss JJJJ-MM-TT sein.");
    else if (opts.heute && fm.datum !== opts.heute) {
      warnungen.push(`[Spec \xA7 8] datum ist ${fm.datum}, heute ist ${opts.heute} \u2014 stimmt das?`);
    }
  }
  if (opts.toolStand && fm.tool_stand_gelesen && fm.tool_stand_gelesen !== opts.toolStand) {
    fehler.push(
      `[Spec \xA7 0/8] tool_stand_gelesen ist ${fm.tool_stand_gelesen}, aber _KI-TOOL-STAND.md hat stand: ${opts.toolStand}. Lies die aktuelle Fassung und trag deren Datum ein.`
    );
  }
  if (opts.niveau && fm.kurs_niveau && fm.kurs_niveau !== opts.niveau) {
    fehler.push(`[Spec \xA7 8/10] kurs_niveau ist \u201E${fm.kurs_niveau}\u201C, der Auftrag verlangt \u201E${opts.niveau}\u201C.`);
  }
  for (const [du, sie] of [["kurzbeschreibung", "kurzbeschreibung_sie"], ["langbeschreibung", "langbeschreibung_sie"]]) {
    if (fm[du] && fm[sie] && fm[du] !== fm[sie]) {
      fehler.push(`[Spec \xA7 6/8] ${sie} muss wortgleich mit ${du} sein (beide in Du-Form).`);
    }
  }
  if (fm.kurzbeschreibung && /^kostenlos/i.test(fm.kurzbeschreibung)) {
    fehler.push("[Spec \xA7 8] kurzbeschreibung beginnt mit \u201EKostenlos\u201C \u2014 weglassen.");
  }
  const lang = fm.langbeschreibung?.replace(/\\n/g, "\n").trim();
  if (lang && (lang.length < 1700 || lang.length > 2400)) {
    warnungen.push(`[Spec \xA7 8] langbeschreibung hat ${lang.length} Zeichen, Ziel sind 1700\u20132400.`);
  }
  const headings = md.split("\n").map((l, i) => ({ text: l.trim(), line: i })).filter((h) => /^## /.test(h.text));
  const lessonIdx = headings.map((h, i) => /^## Lektion \d+/.test(h.text) ? i : -1).filter((i) => i >= 0);
  const dsIdx = headings.map((h, i) => h.text === DATENSCHUTZ ? i : -1).filter((i) => i >= 0);
  if (dsIdx.length !== 1) {
    fehler.push(`[Spec \xA7 3/9] Die \xDCberschrift \u201E${DATENSCHUTZ}\u201C muss genau einmal vorkommen (gefunden: ${dsIdx.length}).`);
  } else if (lessonIdx.length && dsIdx[0] < lessonIdx[lessonIdx.length - 1]) {
    fehler.push(`[Spec \xA7 9] \u201E${DATENSCHUTZ}\u201C steht vor der letzten Lektion \u2014 sie geh\xF6rt direkt hinter die letzte Lektion.`);
  }
  if (lessonIdx.length && (lessonIdx.length < 8 || lessonIdx.length > 10)) {
    fehler.push(`[Spec \xA7 5] Der Kurs hat ${lessonIdx.length} Lektionen, verlangt sind 8\u201310.`);
  }
  if (fm.kurs_niveau === "fortgeschritten") {
    const vIdx = headings.findIndex((h) => h.text === "## Voraussetzungen");
    if (vIdx < 0) fehler.push("[Spec \xA7 10 F1] Abschnitt \u201E## Voraussetzungen\u201C fehlt (Pflicht bei fortgeschritten).");
    else if (lessonIdx.length && vIdx > lessonIdx[0]) {
      fehler.push("[Spec \xA7 10 F1] \u201E## Voraussetzungen\u201C muss vor Lektion 1 stehen (direkt nach der Einleitung).");
    }
    const last = headings[headings.length - 1];
    if (!headings.some((h) => h.text === "## Quellen")) {
      fehler.push("[Spec \xA7 10 F4] Abschnitt \u201E## Quellen\u201C fehlt (Pflicht bei fortgeschritten).");
    } else if (last?.text !== "## Quellen") {
      fehler.push("[Spec \xA7 9] \u201E## Quellen\u201C muss der letzte Abschnitt der Datei sein.");
    }
  }
  return { fehler, warnungen };
}
function readToolStand(kursPath) {
  try {
    const t = readFileSync(join(dirname(kursPath), "..", "_KI-TOOL-STAND.md"), "utf8");
    return t.match(/^stand:\s*(\d{4}-\d{2}-\d{2})/m)?.[1];
  } catch {
    return void 0;
  }
}
function main(argv) {
  const args = [...argv];
  let niveau;
  const n = args.indexOf("--niveau");
  if (n >= 0) {
    niveau = args[n + 1];
    args.splice(n, 2);
  }
  if (args.length !== 1 || niveau && !["einsteiger", "fortgeschritten"].includes(niveau)) {
    console.error("Aufruf: node kurs-check.mjs <absoluter/pfad/content/<slug>.md> [--niveau einsteiger|fortgeschritten]");
    return 2;
  }
  const path = resolve(args[0]);
  let md;
  try {
    md = readFileSync(path, "utf8");
  } catch (e) {
    console.error(`Datei nicht lesbar: ${path} (${e.message})`);
    return 2;
  }
  const slug = basename(path).replace(/\.md$/, "");
  const fehler = [];
  if (basename(dirname(path)) !== "content" || basename(dirname(dirname(path))) !== "WHITESTAG.ACADEMY") {
    fehler.push("[Spec \xA7 9] Die Datei liegt nicht in WHITESTAG.ACADEMY/content/ \u2014 dort muss sie liegen.");
  }
  const r = checkCourse(slug, md, {
    niveau,
    toolStand: readToolStand(path),
    heute: (/* @__PURE__ */ new Date()).toLocaleDateString("sv-SE", { timeZone: "Europe/Berlin" })
  });
  fehler.push(...r.fehler);
  console.log(`kurs-check ${slug}: ${fehler.length ? `FEHLER (${fehler.length})` : "OK"}`);
  fehler.forEach((f, i) => console.log(`  ${i + 1}. ${f}`));
  if (r.warnungen.length) {
    console.log("Warnungen (kein Fehler, aber pr\xFCfen):");
    r.warnungen.forEach((w) => console.log(`  - ${w}`));
  }
  return fehler.length ? 1 : 0;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  process.exitCode = main(process.argv.slice(2));
}
export {
  checkCourse
};
