import unittest

import umschalter as u

PROFILE = {"model": "claude-sonnet-5",
           "env": {"ANTHROPIC_BASE_URL": u.plain("http://localhost:4711/anthropic")}}
CLAUDE_CFG = {"model": "claude-sonnet-5", "maxTurnsPerRun": 80,
              "env": {"ANTHROPIC_BASE_URL": u.plain("http://localhost:4711/anthropic"),
                      "ANDERES": u.plain("bleibt")}}
M = "qwen3.8-flash-next-unsloth-ud-q4_k_xl"


class Modus(unittest.TestCase):
    def test_claude(self):
        self.assertEqual(u.detect_mode(CLAUDE_CFG, PROFILE), "claude")

    def test_strata(self):
        cfg = {**CLAUDE_CFG, **u.strata_patch(CLAUDE_CFG, M)}
        self.assertEqual(u.detect_mode(cfg, PROFILE), "strata")

    def test_fremd_bei_anderem_modell(self):
        self.assertEqual(u.detect_mode({**CLAUDE_CFG, "model": "claude-opus-5"}, PROFILE), "fremd")


class Patches(unittest.TestCase):
    def test_hin_und_zurueck_ergibt_ausgangszustand(self):
        s = {**CLAUDE_CFG, **u.strata_patch(CLAUDE_CFG, M)}
        c = {**s, **u.claude_patch(s, PROFILE)}
        self.assertEqual(c["model"], CLAUDE_CFG["model"])
        self.assertEqual(c["env"], CLAUDE_CFG["env"])

    def test_strata_verdraengt_login_und_behaelt_fremde_env(self):
        p = u.strata_patch(CLAUDE_CFG, M)
        self.assertEqual(p["env"]["ANTHROPIC_AUTH_TOKEN"]["value"], "strata-local")
        self.assertEqual(p["env"]["ANTHROPIC_BASE_URL"]["value"], u.STRATA_BASE)
        self.assertEqual(p["env"]["ANDERES"]["value"], "bleibt")
        self.assertEqual(p["model"], M)


class Entscheidung(unittest.TestCase):
    def test_strata_weg_sofort_claude(self):
        a, _ = u.decide({}, False, None, "strata", True, M)
        self.assertEqual(a, "to_claude")

    def test_zurueck_erst_nach_zwei_gesunden(self):
        a, st = u.decide({}, True, M, "claude", False, "claude-sonnet-5")
        self.assertIsNone(a)
        a, _ = u.decide(st, True, M, "claude", False, "claude-sonnet-5")
        self.assertEqual(a, "to_strata")

    def test_kein_wechsel_waehrend_lauf(self):
        a, _ = u.decide({"oks": 5}, True, M, "claude", True, "claude-sonnet-5")
        self.assertIsNone(a)

    def test_aussetzer_setzt_zaehler_zurueck(self):
        _, st = u.decide({"oks": 1}, False, None, "claude", False, "claude-sonnet-5")
        a, _ = u.decide(st, True, M, "claude", False, "claude-sonnet-5")
        self.assertIsNone(a)

    def test_fremd_haelt_still(self):
        a, _ = u.decide({}, False, None, "fremd", False, "x")
        self.assertIsNone(a)

    def test_neues_strata_modell_wird_nachgezogen(self):
        a, _ = u.decide({}, True, "qwen-neu", "strata", False, M)
        self.assertEqual(a, "to_strata")

    def test_gesund_auf_strata_nichts_tun(self):
        a, _ = u.decide({}, True, M, "strata", False, M)
        self.assertIsNone(a)


if __name__ == "__main__":
    unittest.main()
