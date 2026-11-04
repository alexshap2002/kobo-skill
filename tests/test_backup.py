from __future__ import annotations

import json
import unittest
import zipfile

from fake_kobo import FULL, OLENA, simple_content, submission
from helpers import KoboTestCase


def answers():
    return [
        submission(1, name="Олена", city="kyiv", kids=[{"kids/age": "5"}, {"kids/age": "7"}],
                   _attachments=[{"download_url": "http://x/photo.jpg", "filename": "photo.jpg"}]),
        submission(2, name="Петро", city="lviv"),
        submission(3, name="Іра", city="kyiv"),
    ]


class BackupTest(KoboTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fake.add_form("aForm", "Опитування: «Зима»/2026", submissions=answers(),
                           shared={"kobo_edobro": FULL})
        self.login()

    def test_backup_writes_all_files_without_token(self):
        code, out, err = self.run_cli("backup", "aForm")
        self.assertEqual(code, 0, err)
        [copy] = self.backup_dirs("aForm")
        self.assertIn(str(copy), out)
        self.assertTrue(copy.parent.name.endswith("__aForm"))
        self.assertNotIn("/", copy.parent.name.replace("__aForm", ""))
        names = {p.name for p in copy.iterdir()}
        self.assertEqual(names, {"asset.json", "form.xlsx", "versions.json", "submissions.json",
                                 "submissions.xlsx", "ПРО_КОПІЮ.txt"})
        for p in copy.iterdir():
            self.assertNotIn(OLENA.encode(), p.read_bytes(), p.name)
        self.assertEqual([s["_id"] for s in json.loads((copy / "submissions.json").read_text())], [1, 2, 3])
        versions = json.loads((copy / "versions.json").read_text())
        self.assertEqual([v["uid"] for v in versions], ["v1"])
        self.assertEqual(versions[0]["content"]["survey"][0]["name"], "name")
        with zipfile.ZipFile(copy / "submissions.xlsx") as z:
            sheets = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
        for text in ("Ім&apos;я", "Київ", "Львів", "Вік", "Олена"):
            self.assertIn(text, sheets.replace("'", "&apos;"))
        self.assertEqual(self.fake.calls("GET", "photo"), [], "photos are never copied")

    def test_backup_keeps_newest_five(self):
        for _ in range(7):
            code, out, err = self.run_cli("backup", "aForm")
            self.assertEqual(code, 0, err)
        dirs = self.backup_dirs("aForm")
        self.assertEqual(len(dirs), 5)
        code, out, err = self.run_cli("backups", "aForm")
        self.assertEqual(code, 0, err)
        self.assertIn(dirs[-1].name, out)
        self.assertNotIn(".unfinished", "".join(p.name for p in dirs[0].parent.iterdir()))

    def test_backup_handles_many_pages(self):
        self.fake.max_page = 2
        self.fake.data["aForm"] += [submission(i, name=f"N{i}") for i in range(4, 8)]
        self.run_cli("backup", "aForm")
        [copy] = self.backup_dirs("aForm")
        self.assertEqual(len(json.loads((copy / "submissions.json").read_text())), 7)

    def test_backup_reuses_deployed_versions(self):
        self.run_cli("backup", "aForm")
        self.fake.log.clear()
        self.run_cli("backup", "aForm")
        self.assertEqual(self.fake.calls("GET", "/versions/"), [])

    def test_backup_of_a_never_deployed_form(self):
        self.fake.add_form("aDraft", "Чернетка", deployed=False)
        code, out, err = self.run_cli("backup", "aDraft")
        self.assertEqual(code, 0, err)
        [copy] = self.backup_dirs("aDraft")
        self.assertEqual(json.loads((copy / "submissions.json").read_text()), [])

    def test_failed_backup_leaves_no_copy(self):
        self.fake.fail[("GET", "/api/v2/assets/aForm/data/")] = [500] * 4
        code, out, err = self.run_cli("backup", "aForm")
        self.assertEqual(code, 2)
        self.assertEqual(self.backup_dirs("aForm"), [])

    def test_restore_form_backs_up_first_and_redeploys(self):
        self.run_cli("backup", "aForm")
        broken = simple_content()
        broken["survey"] = broken["survey"][:1]
        form = self.fake.assets["aForm"]
        form["content"] = broken
        form["version_id"] = "vBad"
        form["versions"]["vBad"] = {"content": broken, "deployed": True}
        form["deployed_version_id"] = "vBad"
        self.fake.log.clear()
        code, out, err = self.run_cli("restore-form", "aForm", "--backup", "latest")
        self.assertEqual(code, 0, err)
        self.assertEqual(form["content"]["survey"], simple_content()["survey"])
        self.assertEqual(len(self.backup_dirs("aForm")), 2, "a fresh copy was taken before restoring")
        order = [(m, p) for m, p, _ in self.fake.log]
        self.assertLess(order.index(("GET", "/api/v2/assets/aForm/data/")),
                        order.index(("PATCH", "/api/v2/assets/aForm/")))
        [redeploy] = self.fake.calls("PATCH", "/deployment/")
        self.assertEqual(redeploy[2]["version_id"], form["version_id"])
        self.assertEqual(form["deployed_version_id"], form["version_id"])

    def test_restore_form_survives_rotation_of_its_source(self):
        for _ in range(5):
            self.run_cli("backup", "aForm")
        oldest = self.backup_dirs("aForm")[0]
        self.fake.assets["aForm"]["content"] = {"survey": [], "choices": []}
        code, out, err = self.run_cli("restore-form", "aForm", "--backup", str(oldest))
        self.assertEqual(code, 0, err)
        self.assertFalse(oldest.exists(), "rotation removed the source after it was read")
        self.assertEqual(self.fake.assets["aForm"]["content"]["survey"], simple_content()["survey"])

    def test_restore_form_refuses_a_copy_of_another_form(self):
        self.fake.add_form("bForm", "Інша")
        self.run_cli("backup", "bForm")
        [other] = self.backup_dirs("bForm")
        code, out, err = self.run_cli("restore-form", "aForm", "--backup", str(other))
        self.assertEqual(code, 2)
        self.assertEqual(self.fake.calls("PATCH"), [])


if __name__ == "__main__":
    unittest.main()
