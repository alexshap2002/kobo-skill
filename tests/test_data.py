from __future__ import annotations

import csv
import json
import unittest
import zipfile

from fake_kobo import FULL, submission
from helpers import KoboTestCase, kobo


class DataTest(KoboTestCase):
    def setUp(self) -> None:
        super().setUp()
        photo = {"download_url": f"{self.fake.url}/api/v2/assets/aForm/data/1/attachments/att1/",
                 "filename": "olena/attachments/x/uuid-1/фото 1.jpg", "uid": "att1"}
        self.fake.files["att1"] = b"JPEG"
        answers = [submission(1, name="Олена", city="kyiv", _attachments=[photo]),
                   submission(2, name="Петро", city="lviv"), submission(3, name="Іра", city="kyiv")]
        self.fake.add_form("aForm", "Анкета", submissions=answers, shared={"kobo_edobro": FULL})
        self.login()

    def ids(self) -> list[int]:
        return [r["_id"] for r in self.fake.data["aForm"]]

    def test_export_xlsx_uses_labels(self):
        out = self.tmp / "звіт.xlsx"
        code, text, err = self.run_cli("export", "aForm", "--out", str(out))
        self.assertEqual(code, 0, err)
        with zipfile.ZipFile(out) as z:
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("Місто", sheet)
        self.assertIn("Львів", sheet)
        self.assertNotIn(">lviv<", sheet)

    def test_export_csv_and_json(self):
        out = self.tmp / "звіт.csv"
        code, text, err = self.run_cli("export", "aForm", "--format", "csv", "--out", str(out))
        self.assertEqual(code, 0, err)
        self.assertTrue(out.read_bytes().startswith(b"\xef\xbb\xbf"), "Excel needs the BOM for Cyrillic")
        rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
        self.assertIn("Місто", rows[0])
        self.assertEqual(len(rows), 4)
        out = self.tmp / "звіт.json"
        self.run_cli("export", "aForm", "--format", "json", "--out", str(out))
        self.assertEqual([r["_id"] for r in json.loads(out.read_text(encoding="utf-8"))], [1, 2, 3])

    def test_attachments_downloads_files(self):
        out = self.tmp / "фото"
        code, text, err = self.run_cli("attachments", "aForm", "--out", str(out))
        self.assertEqual(code, 0, err)
        self.assertEqual((out / "1" / "фото 1.jpg").read_bytes(), b"JPEG")

    def test_set_values_backs_up_first(self):
        code, text, err = self.run_cli("set-values", "aForm", "--ids", "1,2", "--set", "city=lviv")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.backup_dirs("aForm")), 1)
        [call] = self.fake.calls("PATCH", "/data/bulk/")
        self.assertEqual(call[2], {"payload": {"submission_ids": [1, 2], "data": {"city": "lviv"}}})
        self.assertEqual(self.fake.data["aForm"][0]["city"], "lviv")

    def test_set_values_refuses_unknown_question_and_repeat_fields(self):
        code, text, err = self.run_cli("set-values", "aForm", "--ids", "1", "--set", "citty=lviv")
        self.assertEqual(code, 2)
        self.assertIn("citty", err)
        code, text, err = self.run_cli("set-values", "aForm", "--ids", "1", "--set", "kids/age=3")
        self.assertEqual(code, 2)
        self.assertEqual(self.fake.calls("PATCH"), [])

    def test_set_status(self):
        code, text, err = self.run_cli("set-status", "aForm", "--ids", "1,3", "--status", "approved")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fake.data["aForm"][2]["_validation_status"], {"uid": "validation_status_approved"})
        self.assertEqual(len(self.backup_dirs("aForm")), 1)

    def test_delete_without_yes_only_previews(self):
        code, text, err = self.run_cli("delete-submissions", "aForm", "--ids", "1,2")
        self.assertEqual(code, 1)
        self.assertIn("фото", text)
        self.assertIn("--yes", text)
        code, text, err = self.run_cli("delete-form", "aForm")
        self.assertEqual(code, 1)
        self.assertIn("3", text)
        self.assertEqual(self.fake.calls("DELETE"), [])
        self.assertEqual(self.backup_dirs("aForm"), [])

    def test_delete_submissions_backs_up_first(self):
        code, text, err = self.run_cli("delete-submissions", "aForm", "--ids", "1-2", "--yes")
        self.assertEqual(code, 0, err)
        [copy_dir] = self.backup_dirs("aForm")
        self.assertEqual(len(json.loads((copy_dir / "submissions.json").read_text())), 3)
        self.assertEqual(self.ids(), [3])
        self.assertIn(str(copy_dir), text)

    def test_delete_refuses_unknown_ids(self):
        code, text, err = self.run_cli("delete-submissions", "aForm", "--ids", "2,99", "--yes")
        self.assertEqual(code, 2)
        self.assertIn("99", err)
        self.assertEqual(self.ids(), [1, 2, 3])

    def test_delete_form_backs_up_first(self):
        code, text, err = self.run_cli("delete-form", "aForm", "--yes")
        self.assertEqual(code, 0, err)
        self.assertNotIn("aForm", self.fake.assets)
        self.assertEqual(len(self.backup_dirs("aForm")), 1)
        self.assertIn("7 днів", text)

    def test_api_write_copies_the_form_first(self):
        body = self.tmp / "body.json"
        body.write_text(json.dumps({"name": "Нова назва"}), encoding="utf-8")
        code, text, err = self.run_cli("api", "PATCH", "/api/v2/assets/aForm/", "--data", str(body))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.fake.assets["aForm"]["name"], "Нова назва")
        self.assertEqual(len(self.backup_dirs("aForm")), 1)
        code, text, err = self.run_cli("api", "GET", "/api/v2/assets/aForm/")
        self.assertEqual(json.loads(text)["uid"], "aForm")

    def test_api_guards_the_rules(self):
        body = self.tmp / "body.json"
        body.write_text(json.dumps({"content": {"survey": []}}), encoding="utf-8")
        refused = [
            ("POST", "/api/v2/assets/", ["--data", str(body)]),  # new forms: create asks for the organisation
            ("DELETE", "/api/v2/assets/aForm/", []),  # delete-form previews and copies
            ("DELETE", "/api/v2/assets/aForm/data/1/", []),  # delete-submissions previews and copies
            ("PATCH", "/api/v2/assets/aForm/", ["--data", str(body)]),  # update-form checks answered questions
            ("DELETE", "/api/v2/assets/aForm/permission-assignments/x/", []),  # unshare-user keeps main accounts
            ("GET", "https://evil.example.org/api/v2/assets/", []),
        ]
        for method, path, extra in refused:
            code, text, err = self.run_cli("api", method, path, *extra)
            self.assertEqual(code, 2, (method, path))
        self.assertEqual([c for c in self.fake.log if c[0] != "GET"], [])
        self.assertIn("aForm", self.fake.assets)

    def test_counts_read_as_natural_ukrainian(self):
        self.assertEqual([kobo.answers_n(n) for n in (1, 2, 5, 11, 21, 22, 25, 112)],
                         ["1 відповідь", "2 відповіді", "5 відповідей", "11 відповідей", "21 відповідь",
                          "22 відповіді", "25 відповідей", "112 відповідей"])
        code, text, err = self.run_cli("delete-submissions", "aForm", "--ids", "1,2", "--yes")
        self.assertIn("Видалено 2 відповіді", text)
        self.assertNotIn("адміністратору Олександр", text + err)

if __name__ == "__main__":
    unittest.main()
