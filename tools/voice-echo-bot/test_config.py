import json
import os
import tempfile
import unittest

import config


class TestLoadEnv(unittest.TestCase):
    def test_parses_quoted_and_export_lines_ignoring_comments(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write('# comment\n')
            f.write('\n')
            f.write('export TELEGRAM_BOT_TOKEN="abc:123"\n')
            f.write('TELEGRAM_ALLOWED_USER_ID="8311805232"\n')
            path = f.name
        self.addCleanup(os.unlink, path)
        env = config.load_env(path)
        self.assertEqual(env["TELEGRAM_BOT_TOKEN"], "abc:123")
        self.assertEqual(env["TELEGRAM_ALLOWED_USER_ID"], "8311805232")
        self.assertNotIn("# comment", env)


class TestWhitestagEnvPath(unittest.TestCase):
    def test_whitestag_env_is_absolute_dotfile_path(self):
        self.assertTrue(config.WHITESTAG_ENV.endswith(".whitestag.env"))
        self.assertTrue(os.path.isabs(config.WHITESTAG_ENV))


class TestLoadToken(unittest.TestCase):
    def test_reads_localhost_3100_token(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"credentials": {"http://localhost:3100": {"token": "tok-xyz"}}}, f)
            path = f.name
        self.addCleanup(os.unlink, path)
        self.assertEqual(config.load_paperclip_token(path), "tok-xyz")


class TestAcademyDefaults(unittest.TestCase):
    def test_academy_defaults_present(self):
        self.assertTrue(config.ACADEMY_INTENT_PATH.endswith("academy-auto/intent.json"))
        self.assertTrue(config.ACADEMY_AUTO_DIR.endswith("scripts/academy-auto"))


if __name__ == "__main__":
    unittest.main()
