from __future__ import annotations

import json
import unittest

from fake_kobo import FULL
from helpers import KoboTestCase


class SharingTest(KoboTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fake.add_form("aShared", "Повна", shared={"kobo_edobro": FULL})
        self.fake.add_form("aNone", "Нічия")
        self.fake.add_form("aPartial", "Половинчаста", shared={"kobo_ymbefree": ["view_asset", "view_submissions"]})
        self.fake.add_form("aForeign", "Чужа", owner="petro", shared={"olena": ["view_asset"]})

    def test_forms_reports_sharing_state(self):
        self.login()
        code, out, err = self.run_cli("forms", "--json")
        self.assertEqual(code, 0, err)
        forms = {f["uid"]: f for f in json.loads(out)}
        self.assertEqual(set(forms), {"aShared", "aNone", "aPartial", "aForeign"})
        self.assertEqual(forms["aShared"]["sharing"], {"bud-vilnyi": "none", "ye-dobro": "full"})
        self.assertEqual(forms["aPartial"]["sharing"]["bud-vilnyi"], "partial")
        self.assertTrue(forms["aNone"]["mine"])
        self.assertFalse(forms["aForeign"]["mine"])
        code, out, err = self.run_cli("forms")
        self.assertIn("«Нічия»", out)
        self.assertIn("власник: petro", out)

    def test_check_sharing_lists_unshared_and_partial(self):
        self.login()
        code, out, err = self.run_cli("check-sharing")
        self.assertEqual(code, 1)
        self.assertIn("aNone", out)
        self.assertIn("aPartial", out)
        self.assertNotIn("aShared", out)
        self.assertNotIn("aForeign", out, "only forms the employee owns are checked")
        self.assertIn("Будь вільний", out)
        self.assertIn("--org", out)
        code, out, err = self.run_cli("check-sharing", "--json")
        problems = {p["uid"] for p in json.loads(out)["problems"]}
        self.assertEqual(problems, {"aNone", "aPartial"})

    def test_daily_check_runs_once_per_day_and_is_silent_without_setup(self):
        code, out, err = self.run_cli("check-sharing", "--daily")
        self.assertEqual((code, out, err), (0, "", ""))
        self.login()
        code, out, err = self.run_cli("check-sharing", "--daily")
        self.assertEqual(code, 0)
        self.assertIn("aNone", out)
        code, out, err = self.run_cli("check-sharing", "--daily")
        self.assertIn("aNone", out, "an unresolved form is raised again, not hidden for the day")
        self.run_cli("share", "aNone", "--org", "ye-dobro")
        self.run_cli("share", "aPartial", "--org", "bud-vilnyi")
        code, out, err = self.run_cli("check-sharing", "--daily")
        self.assertEqual((code, out), (0, ""))
        self.fake.log.clear()
        code, out, err = self.run_cli("check-sharing", "--daily")
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(self.fake.calls(), [], "a clean check is not repeated the same day")

    def test_daily_check_is_silent_when_kobo_is_down(self):
        self.login()
        self.fake.fail[("GET", "/api/v2/assets/")] = [503] * 10
        code, out, err = self.run_cli("check-sharing", "--daily")
        self.assertEqual((code, out, err), (0, "", ""))

    def test_share_adds_only_missing_permissions_one_by_one(self):
        self.login()
        code, out, err = self.run_cli("share", "aPartial", "--org", "bud-vilnyi")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fake.perms_of("aPartial", "kobo_ymbefree"), set(FULL))
        posts = self.fake.calls("POST", "permission-assignments")
        self.assertEqual(len(posts), len(FULL) - 2)
        self.assertTrue(all("/bulk/" not in path for _, path, _ in posts))
        self.assertNotIn("partial_submissions", json.dumps([b for _, _, b in posts]))
        self.assertIn("Будь вільний", out)

    def test_share_both_orgs_and_never_touches_other_users(self):
        self.login()
        before_petro = self.fake.perms_of("aNone", "olena")
        code, out, err = self.run_cli("share", "aNone", "--org", "both")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fake.perms_of("aNone", "kobo_ymbefree"), set(FULL))
        self.assertEqual(self.fake.perms_of("aNone", "kobo_edobro"), set(FULL))
        self.assertEqual(self.fake.perms_of("aNone", "olena"), before_petro)
        self.assertEqual(self.fake.calls("DELETE"), [])

    def test_share_requires_org(self):
        self.login()
        with self.assertRaises(SystemExit):
            self.run_cli("share", "aNone")
        with self.assertRaises(SystemExit):
            self.run_cli("share", "aNone", "--org", "somewhere")
        self.assertEqual(self.fake.calls("POST"), [])

    def test_share_user_and_unshare_user(self):
        self.login()
        code, out, err = self.run_cli("share-user", "aNone", "petro", "--role", "view")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fake.perms_of("aNone", "petro"), {"view_asset", "view_submissions"})
        code, out, err = self.run_cli("unshare-user", "aNone", "petro")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fake.perms_of("aNone", "petro"), set())

    def test_main_accounts_cannot_be_unshared(self):
        self.login()
        code, out, err = self.run_cli("unshare-user", "aShared", "kobo_edobro")
        self.assertEqual(code, 2)
        self.assertEqual(self.fake.perms_of("aShared", "kobo_edobro"), set(FULL))
        self.assertEqual(self.fake.calls("DELETE"), [])


if __name__ == "__main__":
    unittest.main()
