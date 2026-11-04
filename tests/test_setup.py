from __future__ import annotations

import os
import stat
import sys
import unittest

from fake_kobo import MAIN, OLENA
from helpers import KoboTestCase, kobo


class SetupTest(KoboTestCase):
    def test_setup_saves_token_privately_and_never_prints_it(self):
        code, out, err = self.run_cli("setup", stdin=f"  {OLENA}\n")
        self.assertEqual(code, 0, err)
        self.assertIn("olena", out)
        self.assertNotIn(OLENA, out + err)
        token_file = self.home / "token"
        self.assertEqual(token_file.read_text().strip(), OLENA)
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(os.stat(token_file).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(self.home).st_mode), 0o700)

    def test_setup_refuses_main_account(self):
        code, out, err = self.run_cli("setup", stdin=MAIN)
        self.assertEqual(code, 2)
        self.assertIn("головн", out + err)
        self.assertFalse((self.home / "token").exists())
        self.assertNotIn(MAIN, out + err)

    def test_setup_rejects_bad_key(self):
        code, out, err = self.run_cli("setup", stdin="d" * 40)
        self.assertEqual(code, 2)
        self.assertIn("eu.kobotoolbox.org", out + err)
        self.assertFalse((self.home / "token").exists())
        self.assertNotIn("Traceback", out + err)
        self.fake.log.clear()
        code, out, err = self.run_cli("setup", stdin="my password 123")
        self.assertEqual(code, 2)
        self.assertEqual(self.fake.calls(), [], "a non-key must not even be sent to Kobo")

    def test_whoami_without_setup_explains_next_step(self):
        code, out, err = self.run_cli("whoami")
        self.assertEqual(code, 2)
        self.assertIn("ще не налаштовано", out + err)
        self.login()
        code, out, err = self.run_cli("whoami")
        self.assertEqual(code, 0)
        self.assertIn("olena", out)

    def test_client_refuses_foreign_origin(self):
        client = kobo.Kobo(self.fake.url, OLENA)
        with self.assertRaises(kobo.KoboError):
            client.get("https://evil.example.org/api/v2/assets/")
        with self.assertRaises(kobo.KoboError):
            client.get(self.fake.url.replace("127.0.0.1", "localhost") + "/me/")
        self.assertEqual(client.get(self.fake.url + "/me/")["username"], "olena")

    def test_server_errors_are_retried_then_explained(self):
        self.login()
        self.fake.fail[("GET", "/me/")] = [503]
        code, out, err = self.run_cli("whoami")
        self.assertEqual(code, 0, "one 503 is retried")
        self.fake.log.clear()
        self.fake.fail[("GET", "/me/")] = [503] * 4
        code, out, err = self.run_cli("whoami")
        self.assertEqual(code, 2)
        self.assertIn("не відповідає", out + err)
        self.assertNotIn("Traceback", out + err)
        self.assertEqual(len(self.fake.calls("GET", "/me/")), 4, "one try and three retries")

if __name__ == "__main__":
    unittest.main()
