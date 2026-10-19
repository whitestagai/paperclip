"""Rendert ein Changeset als menschenlesbare Freigabe-Liste (Telegram-Dokument)."""

def summary_line(changeset):
    changes = changeset.get("changes", [])
    alt = sum(1 for c in changes if c.get("field") == "alt_text")
    return len(changes), alt

def render_change_list(changeset):
    changes = changeset.get("changes", [])
    site = changeset.get("site", "?")
    count, alt = summary_line(changeset)
    lines = [f"SEO/GEO-Freigabe — {site}",
             f"{count} Änderungen" + (f", davon {alt} Alt-Texte" if alt else ""),
             ""]
    for i, c in enumerate(changes, 1):
        lines.append(f"{i}. {c.get('url','?')}")
        lines.append(f"   Feld: {c.get('field','?')}  (target={c.get('target','?')}, id={c.get('id')})")
        if c.get("old") is not None:
            lines.append(f"   alt: {c.get('old')}")
        lines.append(f"   neu: {c.get('new')}")
        lines.append("")
    return "\n".join(lines)
