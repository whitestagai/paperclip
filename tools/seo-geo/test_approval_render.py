import approval_render as r

CS = {"site": "whitestag.film", "changes": [
    {"url": "https://x/a", "field": "meta_description", "id": 12, "target": "page",
     "new": "Neue Beschreibung", "old": "Alt"},
    {"url": "https://x/b", "field": "alt_text", "id": 99, "target": "media",
     "new": "Ein Foto vom Set"},
]}

def test_summary_counts():
    assert r.summary_line(CS) == (2, 1)

def test_render_contains_fields_and_values():
    text = r.render_change_list(CS)
    assert "whitestag.film" in text
    assert "meta_description" in text
    assert "Neue Beschreibung" in text
    assert "https://x/a" in text
    assert "alt_text" in text

def test_render_shows_old_when_present():
    text = r.render_change_list(CS)
    assert "Alt" in text  # alter Wert wird gezeigt, wenn vorhanden

def test_render_empty_changes():
    assert "0 Änderungen" in r.render_change_list({"site": "s", "changes": []})
