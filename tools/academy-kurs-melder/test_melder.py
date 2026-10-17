import json
import tempfile
import unittest
from pathlib import Path

import melder

LOG = """# Themen
## Freigegebene Themen (Phase 2 — Bau)

| Slug | Titel | Status | is_free | Freigegeben am | Issue |
|---|---|---|---|---|---|
| `nicht-gebaut` | Soll ignoriert werden | offen | ❌ | x | WHI-1 |

## Gebaute Kurse (Phase 2 — fertig)

| Slug | Titel | Status | is_free | Gebaut am | Issue |
|---|---|---|---|---|---|
| `ki-alt` | Alter Kurs | ✅ Gebaut (7 Lektionen) | ❌ kostenpflichtig | 2026-07-06 | WHI-2293 |
{neu}
"""

NEU = "| `ki-neu` | Neuer Kurs | ✅ Gebaut (7 Lektionen), Lektorat GELB [[2026-10-17]] | ✅ kostenlos | [[2026-10-17]] | WHI-10162 / WHI-10163 |"

FM = """---
title: "KI für <Neue> & Co"
zusammenfassung: "Kurzer Überblick."
---
# Text
"""


class MelderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "log.md"
        self.content = self.tmp / "content"
        self.content.mkdir()
        (self.content / "ki-neu.md").write_text(FM, encoding="utf-8")
        self.state = self.tmp / "state.json"
        self.sent = []

    def _run(self, neu="", ok=True):
        self.log.write_text(LOG.format(neu=neu), encoding="utf-8")

        def sender(text):
            self.sent.append(text)
            return ok
        return melder.run(self.log, self.content, self.state, sender=sender)

    def test_parse_nur_gebaute_kurse(self):
        kurse = melder.parse_gebaute_kurse(LOG.format(neu=NEU))
        self.assertEqual(set(kurse), {"ki-alt", "ki-neu"})

    def test_erstlauf_merkt_ohne_senden(self):
        self._run()
        self.assertEqual(self.sent, [])
        self.assertEqual(json.loads(self.state.read_text())["gemeldet"], ["ki-alt"])

    def test_neuer_kurs_wird_einmal_gemeldet(self):
        self._run()
        self._run(NEU)
        self._run(NEU)
        self.assertEqual(len(self.sent), 1)
        msg = self.sent[0]
        self.assertIn("<b>KI für &lt;Neue&gt; &amp; Co</b>", msg)
        self.assertIn("Kurzer Überblick.", msg)
        self.assertIn("7 Lektionen · kostenlos · Lektorat GELB · WHI-10162", msg)

    def test_statusaenderung_alter_zeile_meldet_nicht(self):
        self._run()
        self.log.write_text(LOG.format(neu="").replace(
            "✅ Gebaut (7 Lektionen)", "✅ Gebaut (7 Lektionen), Lektorat GRÜN"), encoding="utf-8")
        melder.run(self.log, self.content, self.state, sender=lambda t: self.sent.append(t) or True)
        self.assertEqual(self.sent, [])

    def test_sendefehler_wird_wiederholt(self):
        self._run()
        self._run(NEU, ok=False)
        self._run(NEU, ok=True)
        self.assertEqual(len(self.sent), 2)
        self.assertIn("ki-neu", json.loads(self.state.read_text())["gemeldet"])

    def test_ohne_kursdatei_faellt_auf_tabellentitel_zurueck(self):
        (self.content / "ki-neu.md").unlink()
        self._run()
        self._run(NEU)
        self.assertIn("<b>Neuer Kurs</b>", self.sent[0])

    def test_leere_tabelle_ueberschreibt_state_nicht(self):
        self._run()
        self.log.write_text("# kaputt\n", encoding="utf-8")
        melder.run(self.log, self.content, self.state, sender=lambda t: True)
        self.assertEqual(json.loads(self.state.read_text())["gemeldet"], ["ki-alt"])


if __name__ == "__main__":
    unittest.main()
