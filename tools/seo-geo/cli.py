import argparse, json, os, shutil, time
from dataclasses import asdict
from config import load_sites, resolve_credential
from apply import apply_changeset

def _site_dir(root, name):
    return os.path.join(os.path.expanduser(root), name)

def _default_client_factory(site, auth):
    from wpclient import WPClient
    return WPClient(site.wp_rest_base, auth)

def _cmd_approve(args, environ):
    src = args.changeset
    dst_dir = os.path.join(os.path.dirname(os.path.dirname(src)), "approved")
    os.makedirs(dst_dir, exist_ok=True)
    shutil.move(src, os.path.join(dst_dir, os.path.basename(src)))
    return 0

def _cmd_apply(args, environ, client_factory):
    site = next(s for s in load_sites(args.sites) if s.name == args.site)
    auth = resolve_credential(site, environ)
    client = client_factory(site, auth)
    sdir = _site_dir(args.root, site.name)
    approved = os.path.join(sdir, "approved")
    applied = os.path.join(sdir, "applied")
    failed = os.path.join(sdir, "failed")
    for fn in sorted(os.listdir(approved)) if os.path.isdir(approved) else []:
        path = os.path.join(approved, fn)
        cs = json.loads(open(path).read())
        log = apply_changeset(cs, client, dry_run=args.dry_run)
        if args.dry_run:
            with open(os.path.join(sdir, f"apply-log.{fn}.json"), "w") as fh:
                json.dump(asdict(log), fh, ensure_ascii=False, indent=2)
            continue
        dest_dir = failed if log.failed else applied
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, f"apply-log.{fn}.json"), "w") as fh:
            json.dump(asdict(log), fh, ensure_ascii=False, indent=2)
        shutil.move(path, os.path.join(dest_dir, fn))
    return 0

def _cmd_audit(args, environ, fetch):
    from audit import run_audit, write_report
    from sitemap import fetch_sitemap_urls  # Task 9
    site = next(s for s in load_sites(args.sites) if s.name == args.site)
    fetch = fetch or _http_fetch
    urls = fetch_sitemap_urls(site, fetch)
    report = run_audit(site, fetch, urls)
    data = json.loads(open(args.sites).read())
    write_report(report, data.get("report_root", "~/.paperclip/seo-geo"))
    return 0

def _cmd_resolve(args, environ, client_factory):
    from resolve import resolve_ids
    site = next(s for s in load_sites(args.sites) if s.name == args.site)
    client = client_factory(site, resolve_credential(site, environ))
    _ep2target = {"pages": "page", "posts": "post"}
    def lookup(target, slug):
        # Agent-Label (page/post) ist unzuverlässig -> zuerst gelabelten Typ, dann den
        # anderen probieren. Nur post+page sind per mu-Plugin schreibbar (nicht Portfolio).
        # Liefert (id, korrigiertes_target) — das target aus dem Typ, wo die ID lag.
        order = ["pages", "posts"] if target == "page" else ["posts", "pages"]
        for e in order:
            wid = client.find_id_by_slug(e, slug)
            if wid is not None:
                return wid, _ep2target[e]
        return None
    cs_in = json.loads(open(os.path.expanduser(args.changeset)).read())
    canonical, unresolved = resolve_ids(cs_in, lookup)
    out = args.out or (os.path.splitext(os.path.expanduser(args.changeset))[0] + "-resolved.json")
    with open(out, "w") as fh:
        json.dump(canonical, fh, ensure_ascii=False, indent=2)
    print(f"AUFGELÖST — {len(canonical['changes'])} Änderungen mit ID -> {out}")
    if unresolved:
        print(f"NICHT auflösbar ({len(unresolved)}):")
        for u in unresolved:
            print(f"  ? {u['url']} ({u['field']})")
    return 1 if unresolved else 0


def _cmd_validate(args, environ, client_factory):
    from changeset import validate_changeset
    cs = json.loads(open(os.path.expanduser(args.changeset)).read())
    problems = validate_changeset(cs)

    if not args.no_live:
        site = next(s for s in load_sites(args.sites) if s.name == args.site)
        client = client_factory(site, resolve_credential(site, environ))
        for i, c in enumerate(cs.get("changes", []), 1):
            err = client.check_editable(c.get("target"), c.get("id"))
            if err:
                problems.append(f"#{i} id={c.get('id')}: {err}")

    n = len(cs.get("changes", []))
    if problems:
        print(f"VALIDIERUNG FEHLGESCHLAGEN — {len(problems)} Problem(e) bei {n} Änderungen:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print(f"VALIDIERUNG OK — {n} Änderungen, keine Beanstandung.")
    return 0


def _cmd_notify(args, environ, pusher, token_maker):
    import seo_approvals as sa
    from approval_render import render_change_list, summary_line
    from changeset import validate_changeset
    cs = json.loads(open(os.path.expanduser(args.changeset)).read())
    problems = validate_changeset(cs)
    if problems:
        print(f"KEIN PUSH — Changeset unsauber ({len(problems)} Problem(e)):")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    count, alt = summary_line(cs)
    list_dir = os.path.expanduser(args.list_dir); os.makedirs(list_dir, exist_ok=True)
    token = token_maker()
    list_path = os.path.join(list_dir, token + ".txt")
    with open(list_path, "w", encoding="utf-8") as fh:
        fh.write(render_change_list(cs))
    sa.create(os.path.expanduser(args.approvals_dir), args.site,
              os.path.expanduser(args.changeset), list_path, count, alt,
              int(args.chat_id), token=token)
    caption = (f"🟢 SEO-Freigabe {args.site} — {count} Änderungen"
               + (f" ({alt} Alt-Texte)" if alt else ""))
    pusher(caption, list_path, token, int(args.chat_id), args.bot_env)
    print(f"PUSH RAUS — {args.site}, Token {token}")
    return 0

def _default_pusher(caption, list_path, token, chat_id, bot_env):
    from telegram_push import push_approval, load_bot_token
    bot_token = load_bot_token(bot_env)
    push_approval(bot_token, chat_id, caption, list_path, token)

def _cmd_reping(args, environ, pusher, now):
    import seo_approvals as sa
    ad = os.path.expanduser(args.approvals_dir)
    pend = sa.list_pending(ad, older_than_hours=int(args.older_than_hours), now=now)
    n = 0
    for rec in pend:
        if rec.get("last_reping"):
            continue
        days = int((now - rec.get("created", now)) / 86400)
        pusher(rec["chat_id"], "⏳ SEO-Freigabe {} wartet seit {} Tag(en).".format(
            rec["site"], days), args.bot_env)
        # Re-Read vor dem Schreiben: der Bot kann den Token zwischen dem
        # list_pending()-Load und diesem Write bereits auf applied/rejected
        # gesetzt haben. In dem Fall NICHT zurueck auf pending revertieren.
        fresh = sa.load(ad, rec["token"])
        if fresh is not None and fresh.get("status") == "pending":
            fresh["last_reping"] = now
            sa._write_atomic(sa._path(ad, rec["token"]), fresh)
            n += 1
    print(f"RE-PING — {n} Erinnerung(en)")
    return 0

def _default_text_pusher(chat_id, text, bot_env):
    from telegram_push import push_text, load_bot_token
    push_text(load_bot_token(bot_env), chat_id, text)

def _http_fetch(url):
    import requests
    r = requests.get(url, timeout=30); r.raise_for_status()
    # Fehlt der charset im Content-Type (z.B. "text/plain"), raet requests ISO-8859-1
    # und macht aus UTF-8-Bytes Mojibake. Das Web ist praktisch immer UTF-8 —
    # utf-8-sig entfernt zugleich ein evtl. vorhandenes BOM.
    ctype = (r.headers.get("content-type") or "").lower()
    if "charset=" not in ctype:
        return r.content.decode("utf-8-sig", errors="replace")
    return r.text

def main(argv, environ, fetch=None, client_factory=None,
         pusher=None, token_maker=None, now=None) -> int:
    client_factory = client_factory or _default_client_factory
    if token_maker is None:
        token_maker = lambda: os.urandom(9).hex()
    now = time.time() if now is None else now
    p = argparse.ArgumentParser(prog="seo-geo")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit"); a.add_argument("--site"); a.add_argument("--sites")
    ap = sub.add_parser("approve"); ap.add_argument("--changeset"); ap.add_argument("--root")
    apl = sub.add_parser("apply"); apl.add_argument("--site"); apl.add_argument("--sites")
    apl.add_argument("--root"); apl.add_argument("--dry-run", action="store_true")
    v = sub.add_parser("validate"); v.add_argument("--site"); v.add_argument("--sites")
    v.add_argument("--changeset"); v.add_argument("--no-live", action="store_true")
    rs = sub.add_parser("resolve"); rs.add_argument("--site"); rs.add_argument("--sites")
    rs.add_argument("--changeset"); rs.add_argument("--out")
    nt = sub.add_parser("notify")
    for aa in ("--site", "--changeset", "--approvals-dir", "--list-dir",
               "--bot-env", "--chat-id"):
        nt.add_argument(aa)
    rp = sub.add_parser("reping")
    for aa in ("--approvals-dir", "--bot-env", "--older-than-hours"):
        rp.add_argument(aa)
    args = p.parse_args(argv)
    if args.cmd == "resolve": return _cmd_resolve(args, environ, client_factory)
    if args.cmd == "validate": return _cmd_validate(args, environ, client_factory)
    if args.cmd == "approve": return _cmd_approve(args, environ)
    if args.cmd == "apply": return _cmd_apply(args, environ, client_factory)
    if args.cmd == "audit": return _cmd_audit(args, environ, fetch)
    # NB: pusher wird NICHT global gesetzt — notify und reping haben verschiedene
    # Pusher-Signaturen, jeder Command wählt seinen eigenen Default beim Dispatch.
    if args.cmd == "notify": return _cmd_notify(args, environ, pusher or _default_pusher, token_maker)
    if args.cmd == "reping": return _cmd_reping(args, environ, pusher or _default_text_pusher, now)
    return 1

if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:], os.environ))
