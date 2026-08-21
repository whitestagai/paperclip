#!/usr/bin/env python3
"""ctx_report.py — Kontext-Bedarf pro LM-Studio-Modell aus den Server-Logs.

Liest die LM-Studio-Server-Logs (~/.lmstudio/server-logs/YYYY-MM/YYYY-MM-DD.N.log),
ermittelt je Completion-Response das (prompt_tokens, total_tokens) und ordnet es dem
zuletzt gesehenen "model" zu. total_tokens = prompt+completion = das, was gemeinsam
ins Kontextfenster passen muss.

Vergleicht den realen Bedarf (Perzentile über die Vorwoche, MAX über 30 Tage) mit
dem KONFIGURIERTEN Kontextfenster je Modell (aus den LM-Studio-Model-Configs) und
vergibt eine Ampel:
  ROT   = konfiguriert < p99      -> Overflow-Risiko (Kontext wird abgeschnitten)
  GELB  = konfiguriert > 3x p99   -> überdimensioniert (RAM-Verschwendung)
          ODER konfiguriert < 1.2x p99 -> zu wenig Puffer für Ausreißer
  GRÜN  = gesunder Puffer (1.2x .. 3x p99)
  GRAU  = kein konfiguriertes Fenster gefunden (JIT/entladen)

Ausgabe: schreibt HTML nach --out-html und (optional) JSON nach --out-json.
Kein LLM, rein deterministisch.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta

LMS_API = "http://127.0.0.1:1234/api/v0/models"

HOME = os.path.expanduser("~")
LOG_ROOT = os.path.join(HOME, ".lmstudio", "server-logs")
CFG_ROOT = os.path.join(HOME, ".lmstudio", ".internal", "user-concrete-model-default-config")

RE_MODEL = re.compile(r'"model":\s*"([^"]+)"')
RE_PROMPT = re.compile(r'"prompt_tokens":\s*(\d+)')
RE_TOTAL = re.compile(r'"total_tokens":\s*(\d+)')
RE_FNAME = re.compile(r'(\d{4})-(\d{2})-(\d{2})\.\d+\.log$')
# Pfad einer remoten Modell-Kopie: "<32-stelliger geräte-hash>:<publisher>/<ordner>"
RE_DEVPATH = re.compile(r'^([0-9a-f]{32}):(.+)$')

LMS_BIN = os.path.join(HOME, ".lmstudio", "bin", "lms")

SKIP_MODELS = {"text-embedding-bge-m3"}

# Ab wie vielen Tagen ohne Call ein (noch installiertes, entladenes) Modell als still gilt
STALE_DAYS = 3


def log_files_since(cutoff_date):
    """Alle Logdateien mit Dateidatum >= cutoff_date (datetime.date)."""
    out = []
    if not os.path.isdir(LOG_ROOT):
        return out
    for month in os.listdir(LOG_ROOT):
        mdir = os.path.join(LOG_ROOT, month)
        if not os.path.isdir(mdir):
            continue
        for fn in os.listdir(mdir):
            m = RE_FNAME.search(fn)
            if not m:
                continue
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            if d >= cutoff_date:
                out.append((d, os.path.join(mdir, fn)))
    return out


def collect(files):
    """({model: [total_tokens,...]}, {model: letztes_call_datum}) über die Dateien.

    Das Datum stammt aus dem Dateinamen (Logs sind tagesweise rotiert) und dient
    dazu, abgelöste Modelle zu erkennen, die nur noch als Altlast im Fenster liegen."""
    per_model = {}
    last_seen = {}
    if not files:
        return per_model, last_seen
    paths = [p for _, p in files]
    date_of = {p: d for d, p in files}
    # grep reduziert 100e MB auf wenige MB; -H erhält Datei-Grenzen
    proc = subprocess.Popen(
        ["grep", "-H", "-E", r'"model":|"prompt_tokens":|"total_tokens":', *paths],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    cur_model = None
    cur_file = None
    for line in proc.stdout:
        sep = line.find(":")
        if sep < 0:
            continue
        path, content = line[:sep], line[sep + 1:]
        if path != cur_file:
            cur_file = path
            cur_model = None
        m = RE_MODEL.search(content)
        if m:
            cur_model = m.group(1)
            continue
        t = RE_TOTAL.search(content)
        if t and cur_model and cur_model not in SKIP_MODELS:
            per_model.setdefault(cur_model, []).append(int(t.group(1)))
            d = date_of.get(path)
            if d and (cur_model not in last_seen or d > last_seen[cur_model]):
                last_seen[cur_model] = d
    proc.wait()
    return per_model, last_seen


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * q
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return int(sorted_vals[f])
    return int(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def load_configured_ctx():
    """{modell_pfad: ctx} aus den Model-Config-JSONs.

    Schlüssel ist der Pfad relativ zu CFG_ROOT ohne `.json` — er entspricht exakt
    dem `path` des Modells in `lms ls --json`. Nur diese ordner-/pfadbasierte Datei
    wird von LM Studio beim Laden ausgewertet."""
    out = {}
    if not os.path.isdir(CFG_ROOT):
        return out
    for dp, _, fs in os.walk(CFG_ROOT):
        for fn in fs:
            if not fn.endswith(".json") or ".bak" in fn:
                continue
            p = os.path.join(dp, fn)
            try:
                d = json.load(open(p))
            except Exception:
                continue
            ctx = None
            for fld in d.get("load", {}).get("fields", []):
                if fld.get("key") == "llm.load.contextLength":
                    ctx = fld.get("value")
            if ctx is None:
                continue
            out[os.path.relpath(p, CFG_ROOT)[:-len(".json")]] = int(ctx)
    return out


def load_model_index():
    """{identifier: [(geräte_hash|None, pfad)]} aller installierten Modell-Kopien.

    Dasselbe Modell existiert pro Gerät SEPARAT; `lms ls --json` präfixt den Pfad
    remoter Kopien mit dem Geräte-Hash (`<hash>:<publisher>/<ordner>`). Lokale
    Kopien haben kein Präfix. Ohne diese Unterscheidung vergleicht man den geladenen
    Kontext der einen Kopie mit der Default-Config einer anderen."""
    try:
        txt = subprocess.run([LMS_BIN, "ls", "--json"],
                             capture_output=True, text=True, timeout=20).stdout
        data = json.loads(txt)
    except Exception:
        return {}
    data = data if isinstance(data, list) else data.get("models", [])
    idx = {}
    for m in data:
        ident = m.get("modelKey") or m.get("identifier")
        p = m.get("path") or ""
        if not ident or not p:
            continue
        mm = RE_DEVPATH.match(p)
        idx.setdefault(ident, []).append((mm.group(1), mm.group(2)) if mm else (None, p))
    return idx


def load_loaded_ctx():
    """({model_id: loaded_context_length}, {installierte model_ids} | None).

    Der geladene Wert ist der REAL wirksame — er kann von der persistenten
    Default-Config abweichen (GUI-Änderung ohne 'set as default').

    Das zweite Element listet ALLE installierten Modelle, unabhängig vom Ladezustand
    und vom `type` (llm/vlm/embedding) — Modelle, die in den Logs auftauchen, hier
    aber fehlen, sind deinstalliert/abgelöst. `None`, wenn LM Studio nicht erreichbar
    war; dann darf nichts als abgelöst gewertet werden."""
    try:
        with urllib.request.urlopen(LMS_API, timeout=4) as r:
            d = json.load(r)
    except Exception:
        return {}, None
    out = {}
    installed = set()
    for m in d.get("data", []):
        mid = m.get("id")
        if not mid:
            continue
        installed.add(mid)
        cl = m.get("loaded_context_length")
        if m.get("state") == "loaded" and cl:
            out[mid] = int(cl)
    return out, installed


def load_devices():
    """{model_identifier: geräte_klarname} der geladenen Modelle aus `lms ps`.

    Der Klarname ("RTX Pro 6000", "MacbookM5Mx128", "Local") steht NUR in der
    Textausgabe — `lms ps --json` liefert nur einen Geräte-Hash. Deshalb werden die
    Spaltengrenzen aus der Kopfzeile gelesen und die Zeilen danach geschnitten
    (Gerätenamen enthalten Leerzeichen, ein split() reicht nicht). Leeres Dict bei
    jedem Problem — die Device-Spalte ist Zusatzinfo, kein Grund zum Abbruch."""
    try:
        txt = subprocess.run([LMS_BIN, "ps"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return {}
    lines = [l for l in txt.splitlines() if l.strip()]
    hdr = next((l for l in lines if "IDENTIFIER" in l and "DEVICE" in l), None)
    if not hdr:
        return {}
    cols = sorted((hdr.index(c), c) for c in ("IDENTIFIER", "DEVICE") if c in hdr)
    starts = {name: pos for pos, name in cols}
    # Ende einer Spalte = Anfang der nächsten Überschrift rechts davon
    all_starts = sorted(m.start() for m in re.finditer(r"\S+", hdr))

    def slice_col(line, name):
        s = starts[name]
        nxt = [p for p in all_starts if p > s]
        return line[s:nxt[0]].strip() if nxt else line[s:].strip()

    out = {}
    for l in lines[lines.index(hdr) + 1:]:
        ident = slice_col(l, "IDENTIFIER")
        dev = slice_col(l, "DEVICE")
        if ident:
            out[ident] = dev or "Local"
    return out


def load_loaded_paths():
    """({identifier: (geräte_hash|None, pfad)}, {geräte_hash: klarname}).

    Achtung: `lms ps --json` liefert den Pfad OHNE Geräte-Präfix (anders als
    `lms ls --json`) — das Gerät steht ausschließlich in `deviceIdentifier`.
    Wer hier auf ein Pfad-Präfix prüft, hält jede remote Kopie für lokal.

    `lms ps --json` nennt das Gerät nur als Hash, `lms ps` (Text) nur als Klarname —
    über den gemeinsamen Identifier lassen sich beide verbinden, damit auch ENTLADENE
    remote Kopien (die nur im Hash-Pfad auftauchen) benannt werden können."""
    try:
        data = json.loads(subprocess.run([LMS_BIN, "ps", "--json"],
                                         capture_output=True, text=True, timeout=15).stdout)
    except Exception:
        return {}, {}
    names = load_devices()
    paths, hash_names = {}, {}
    for m in data:
        ident = m.get("identifier")
        if not ident:
            continue
        h = m.get("deviceIdentifier")
        if m.get("path"):
            paths[ident] = (h, m["path"])
        if h and ident in names:
            hash_names[h] = names[ident]
    return paths, hash_names


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def resolve_config(model, cfg_map, model_idx, loaded_paths, hash_names):
    """(cfg_ctx, status, gerät) für ein Modell aus den Logs.

    status: "local"  = pfadgenaue Default-Config auf DIESEM Mac gefunden
            "none"   = lokale Kopie, aber keine Default-Config -> nicht festgenagelt
            "remote" = die geladene Kopie liegt auf einem anderen Gerät; dessen
                       Default-Config liegt DORT und ist von hier nicht lesbar
            "unknown" = Modell nicht mehr im Index (deinstalliert)

    Wichtig: es wird die Kopie bewertet, die tatsächlich geladen ist. Früher wurde
    per Namensähnlichkeit gematcht — das verglich regelmäßig die geladene
    MacBook-Kopie mit der Config der gleichnamigen Studio-Kopie und erfand Drift."""
    entry = loaded_paths.get(model)
    if entry:
        dev_hash, path = entry
        if dev_hash:
            return None, "remote", hash_names.get(dev_hash, "anderes Gerät")
        return cfg_map.get(path), ("local" if path in cfg_map else "none"), "Local"
    # Nicht geladen: nur eindeutig, wenn es genau eine Kopie gibt
    entries = model_idx.get(model, [])
    locals_ = [rel for dev, rel in entries if dev is None]
    if len(locals_) == 1 and not [d for d, _ in entries if d]:
        rel = locals_[0]
        return cfg_map.get(rel), ("local" if rel in cfg_map else "none"), "Local"
    if entries:
        devs = {hash_names.get(d, "anderes Gerät") for d, _ in entries if d}
        return None, "remote", ", ".join(sorted(devs)) if devs else "Local"
    return None, "unknown", None


def ampel(ctx, p99, maxv):
    """(farbe_hex, symbol, klartext) je nach Bedarf vs. konfiguriert."""
    if ctx is None:
        return ("#9aa0a6", "—", "kein Fenster konfiguriert (JIT/entladen)")
    if ctx < p99:
        return ("#d93025", "●", f"ROT: Fenster {fmt(ctx)} < p99-Bedarf {fmt(p99)} — Overflow-Risiko, ctx erhöhen")
    if ctx < 1.2 * p99:
        return ("#f9ab00", "●", f"GELB: nur {ctx/max(p99,1):.2f}× p99 — wenig Puffer für Spitzen ({fmt(maxv)})")
    # Überdimensioniert nur, wenn das Fenster selbst die 30-Tage-Spitze mit dickem
    # Puffer übersteigt — sonst fängt es legitim die Ausreißer ab.
    if ctx > 3 * p99 and ctx > 1.3 * maxv:
        return ("#f9ab00", "●", f"GELB: {ctx/max(p99,1):.1f}× p99 (MAX {fmt(maxv)}) — überdimensioniert, RAM sparbar")
    return ("#188038", "●", f"GRÜN: gesunder Puffer ({ctx/max(p99,1):.1f}× p99, MAX {fmt(maxv)})")


def fmt(n):
    return f"{n/1000:.0f}k" if n >= 1000 else str(n)


def build_rows(week, month, cfg_map, loaded_map, installed, dev_map, last_seen, today,
               model_idx, loaded_paths, hash_names):
    rows = []
    for model, vals in week.items():
        v = sorted(vals)
        mvals = sorted(month.get(model, vals))
        p50, p90, p95, p99 = pct(v, .5), pct(v, .9), pct(v, .95), pct(v, .99)
        maxv = mvals[-1] if mvals else v[-1]
        cfg_ctx, cfg_status, cfg_dev = resolve_config(
            model, cfg_map, model_idx, loaded_paths, hash_names)
        loaded_ctx = loaded_map.get(model)
        # Der real wirksame Wert ist der geladene; die Config gilt beim nächsten Load.
        ctx = loaded_ctx if loaded_ctx is not None else cfg_ctx
        device = dev_map.get(model) or cfg_dev
        seen = last_seen.get(model)
        # Abgelöst = taucht in den Logs auf, ist aber nicht mehr installiert. Solche
        # Modelle würden sonst mit ihrer verwaisten Default-Config bis zu 30 Tage
        # lang eine Ampel bekommen, obwohl sie niemand mehr aufruft.
        retired = installed is not None and model not in installed and loaded_ctx is None
        if retired:
            color, sym = "#9aa0a6", "○"
            seen_txt = f", letzter Call {seen.strftime('%d.%m.')}" if seen else ""
            note = f"ABGELÖST: nicht mehr in LM Studio installiert{seen_txt} — keine Bewertung"
            ctx = None
        else:
            color, sym, note = ampel(ctx, p99, maxv)
            # Persistenz-Diskrepanz: geladen ≠ Default-Config -> überlebt Neustart nicht
            if cfg_status == "local" and loaded_ctx is not None and cfg_ctx != loaded_ctx:
                note += (f" · ⚠ nicht festgenagelt: Config {fmt(cfg_ctx)} — beim nächsten "
                         f"Reload gilt wieder {fmt(cfg_ctx)}")
            elif cfg_status == "none" and loaded_ctx is not None:
                note += (" · ⚠ keine Default-Config — der geladene Wert überlebt "
                         "den nächsten Reload nicht")
            elif cfg_status == "remote":
                note += f" · Default-Config liegt auf {cfg_dev}, von hier nicht prüfbar"
            # Still, aber noch installiert: kein Fehler, nur ein Hinweis auf dünne Datenbasis
            if seen and (today - seen).days >= STALE_DAYS and loaded_ctx is None:
                note += f" · seit {seen.strftime('%d.%m.')} keine Calls"
        rows.append({
            "model": model, "calls": len(v), "device": device,
            "last_seen": seen.isoformat() if seen else None, "retired": retired,
            "cfg_status": cfg_status,
            "p50": p50, "p90": p90, "p95": p95, "p99": p99, "max30d": maxv,
            "ctx": ctx, "loaded": loaded_ctx, "config": cfg_ctx,
            "color": color, "sym": sym, "note": note,
        })
    # Abgelöste ans Ende, sonst nach Call-Zahl
    rows.sort(key=lambda r: (r["retired"], -r["calls"]))
    return rows


def render_html(rows, week_from, week_to):
    def td(x, align="right"):
        return f'<td style="padding:6px 10px;text-align:{align};border-bottom:1px solid #eee">{x}</td>'
    head = (
        '<tr style="background:#f1f3f4">'
        + "".join(
            f'<th style="padding:8px 10px;text-align:{a};border-bottom:2px solid #dadce0;font:600 13px sans-serif">{h}</th>'
            for h, a in [("", "center"), ("Modell", "left"), ("Gerät", "left"),
                         ("Calls", "right"),
                         ("p50", "right"), ("p90", "right"), ("p95", "right"),
                         ("p99", "right"), ("MAX 30d", "right"),
                         ("ctx aktiv", "right"), ("Bewertung", "left")])
        + "</tr>"
    )
    body = ""
    for r in rows:
        ctx_disp = fmt(r["ctx"]) if r["ctx"] is not None else "—"
        body += (
            "<tr>"
            + f'<td style="padding:6px 10px;text-align:center;color:{r["color"]};font-size:16px">{r["sym"]}</td>'
            + td(f'<code>{r["model"]}</code>', "left")
            + td(r["device"] or "—", "left")
            + td(f'{r["calls"]:,}'.replace(",", "."))
            + td(fmt(r["p50"])) + td(fmt(r["p90"])) + td(fmt(r["p95"]))
            + f'<td style="padding:6px 10px;text-align:right;border-bottom:1px solid #eee;font-weight:600">{fmt(r["p99"])}</td>'
            + td(fmt(r["max30d"])) + td(ctx_disp)
            + f'<td style="padding:6px 10px;text-align:left;border-bottom:1px solid #eee;color:{r["color"]};font-size:12px">{r["note"]}</td>'
            + "</tr>"
        )
    def names(rs):
        return ", ".join(
            r["model"] + (" (%s)" % r["device"] if r["device"] else "") for r in rs)

    reds = [r for r in rows if r["color"] == "#d93025"]
    yellows = [r for r in rows if r["color"] == "#f9ab00"]
    retired = [r for r in rows if r["retired"]]
    summary = ""
    if reds:
        summary += ("<p style='color:#d93025;font-weight:600'>⚠ " + names(reds)
                    + " unter dem p99-Bedarf — Kontext wird bei Spitzen abgeschnitten.</p>")
    if yellows:
        summary += "<p style='color:#b06000'>Zur Optimierung: " + names(yellows) + ".</p>"
    if not reds and not yellows:
        summary = "<p style='color:#188038;font-weight:600'>✓ Alle konfigurierten Fenster passen zum realen Bedarf.</p>"
    if retired:
        summary += ("<p style='color:#5f6368;font-size:12px'>Nicht bewertet (abgelöst, nur noch "
                    "Alt-Calls im Fenster): " + ", ".join(r["model"] for r in retired) + ".</p>")
    return f"""<div style="font:14px/1.5 -apple-system,sans-serif;color:#202124;max-width:900px">
<h2 style="margin:0 0 4px">Kontext-Bedarf der LM-Studio-Modelle</h2>
<p style="color:#5f6368;margin:0 0 14px">Vorwoche {week_from} – {week_to} · <code>total_tokens</code> = Prompt + Antwort je Call · MAX über 30 Tage</p>
{summary}
<table style="border-collapse:collapse;width:100%;margin:10px 0 16px">{head}{body}</table>
<p style="color:#5f6368;font-size:12px">Ampel: <span style="color:#d93025">●</span> Fenster kleiner als p99-Bedarf (Overflow) ·
<span style="color:#f9ab00">●</span> zu knapp oder überdimensioniert ·
<span style="color:#188038">●</span> gesunder Puffer ·
<span style="color:#9aa0a6">●</span> kein Fenster konfiguriert.
Quelle: <code>~/.lmstudio/server-logs</code> + Model-Configs. Erzeugt vom Skript <code>ctx-stats/ctx_report.py</code>.</p>
</div>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-days", type=int, default=7)
    ap.add_argument("--month-days", type=int, default=30)
    ap.add_argument("--out-html", required=True)
    ap.add_argument("--out-json", default="")
    ap.add_argument("--min-calls", type=int, default=5,
                    help="Modelle mit weniger Calls in der Vorwoche ausblenden")
    args = ap.parse_args()

    today = datetime.now().date()
    week_cut = today - timedelta(days=args.week_days)
    month_cut = today - timedelta(days=args.month_days)

    week, last_seen = collect(log_files_since(week_cut))
    month, _ = collect(log_files_since(month_cut))
    week = {m: v for m, v in week.items() if len(v) >= args.min_calls}

    cfg_map = load_configured_ctx()
    loaded_map, installed = load_loaded_ctx()
    dev_map = load_devices()
    model_idx = load_model_index()
    loaded_paths, hash_names = load_loaded_paths()
    rows = build_rows(week, month, cfg_map, loaded_map, installed, dev_map, last_seen, today,
                      model_idx, loaded_paths, hash_names)

    html = render_html(rows, week_cut.isoformat(), today.isoformat())
    open(args.out_html, "w", encoding="utf-8").write(html)
    if args.out_json:
        json.dump({"generated": today.isoformat(), "rows": rows}, open(args.out_json, "w"), indent=1)
    # Kurzstatus auf stdout
    reds = sum(1 for r in rows if r["color"] == "#d93025")
    ret = sum(1 for r in rows if r["retired"])
    print(f"ctx_report: {len(rows)} Modelle ({ret} abgelöst), {reds} ROT, HTML -> {args.out_html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
