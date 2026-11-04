from __future__ import annotations

import copy
import json
import unittest

from fake_kobo import FULL, fake_xlsx, simple_content, submission
from helpers import KoboTestCase


class FormsTest(KoboTestCase):
    def setUp(self) -> None:
        super().setUp()
        answers = [submission(1, name="Олена", city="kyiv", kids=[{"kids/age": "5"}]), submission(2, name="Іра")]
        self.fake.add_form("aForm", "Анкета", submissions=answers, shared={"kobo_edobro": FULL})
        self.fake.add_form("aEmpty", "Без відповідей", shared={"kobo_edobro": FULL})
        self.login()

    def content_file(self, content: dict) -> str:
        path = self.tmp / "форма.json"
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def new_uids(self) -> list[str]:
        return [uid for uid in self.fake.assets if uid.startswith("new")]

    # --- create ------------------------------------------------------------------------------------

    def test_create_requires_org_and_shares(self):
        f = self.content_file(simple_content())
        with self.assertRaises(SystemExit):
            self.run_cli("create", "--name", "Нова", "--content", f)
        self.assertEqual(self.new_uids(), [])
        code, out, err = self.run_cli("create", "--name", "Нова", "--content", f, "--org", "ye-dobro")
        self.assertEqual(code, 0, err)
        [uid] = self.new_uids()
        self.assertIn(uid, out)
        self.assertEqual(self.fake.assets[uid]["name"], "Нова")
        self.assertEqual(self.fake.perms_of(uid, "kobo_edobro"), set(FULL))
        self.assertEqual(self.fake.perms_of(uid, "kobo_ymbefree"), set())
        self.assertFalse(self.fake.assets[uid]["has_deployment"])
        self.assertIn("Deploy", out, "reminds that the Google sheet appears only after deploying")

    def test_create_normalises_simple_xlsform_style_content(self):
        content = {"survey": [{"type": "select_one yn", "name": "ok", "label": "Добре?"},
                              {"type": "begin group", "name": "g", "label": "Група"},
                              {"type": "text", "name": "t", "label": "Текст"},
                              {"type": "end group"}],
                   "choices": [{"list_name": "yn", "name": "yes", "label": "Так"}]}
        code, out, err = self.run_cli("create", "--name", "Проста", "--content", self.content_file(content),
                                      "--org", "both", "--deploy")
        self.assertEqual(code, 0, err)
        [uid] = self.new_uids()
        sent = self.fake.assets[uid]["content"]
        self.assertEqual(sent["survey"][0]["type"], "select_one")
        self.assertEqual(sent["survey"][0]["select_from_list_name"], "yn")
        self.assertEqual(sent["survey"][0]["label"], ["Добре?"])
        self.assertEqual(sent["survey"][1]["type"], "begin_group")
        self.assertEqual(sent["translations"], [None])
        self.assertTrue(self.fake.assets[uid]["has_deployment"])
        self.assertEqual(self.fake.perms_of(uid, "kobo_ymbefree"), set(FULL))

    def test_create_rejects_select_without_choices(self):
        content = {"survey": [{"type": "select_one missing", "name": "q", "label": "Q"},
                              {"type": "text", "name": "q", "label": "Q2"},
                              {"type": "begin_group", "name": "g"}]}
        code, out, err = self.run_cli("create", "--name", "X", "--content", self.content_file(content),
                                      "--org", "ye-dobro")
        self.assertEqual(code, 2)
        self.assertIn("missing", err)
        self.assertIn("«q»", err)
        self.assertIn("end_group", err)
        self.assertEqual(self.fake.calls("POST"), [])

    def test_create_from_xlsx_uses_import_with_library_false(self):
        path = self.tmp / "моя форма.xlsx"
        path.write_bytes(fake_xlsx())
        code, out, err = self.run_cli("create", "--name", "З Excel", "--xlsx", str(path), "--org", "bud-vilnyi")
        self.assertEqual(code, 0, err)
        [imp] = self.fake.imports.values()
        self.assertEqual(imp["library"], "false")
        uid = imp["asset"]
        self.assertEqual(self.fake.assets[uid]["name"], "З Excel")
        self.assertEqual(self.fake.perms_of(uid, "kobo_ymbefree"), set(FULL))

    def test_clone_shares_new_form(self):
        code, out, err = self.run_cli("create", "--clone-from", "aForm", "--name", "Копія анкети",
                                      "--org", "bud-vilnyi")
        self.assertEqual(code, 0, err)
        [uid] = self.new_uids()
        self.assertEqual(self.fake.assets[uid]["content"]["survey"], simple_content()["survey"])
        self.assertEqual(self.fake.perms_of(uid, "kobo_ymbefree"), set(FULL))

    # --- update ------------------------------------------------------------------------------------

    def test_update_refuses_dropping_answered_question_without_force(self):
        content = simple_content()
        content["survey"] = [r for r in content["survey"] if r.get("name") != "city"]
        f = self.content_file(content)
        code, out, err = self.run_cli("update-form", "aForm", "--content", f)
        self.assertEqual(code, 2)
        self.assertIn("Місто", err)
        self.assertIn("--force", err)
        self.assertEqual(self.fake.calls("PATCH"), [])
        self.assertEqual(self.backup_dirs("aForm"), [], "a refused change takes no copy slot")
        code, out, err = self.run_cli("update-form", "aForm", "--content", f, "--force")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.backup_dirs("aForm")), 1)
        self.assertNotIn("city", [r.get("name") for r in self.fake.assets["aForm"]["content"]["survey"]])

    def test_update_refuses_type_change_of_answered_question(self):
        content = simple_content()
        content["survey"][3]["type"] = "text"  # kids/age: integer -> text, has an answer
        code, out, err = self.run_cli("update-form", "aForm", "--content", self.content_file(content))
        self.assertEqual(code, 2)
        self.assertIn("Вік", err)
        self.assertEqual(self.fake.calls("PATCH"), [])

    def test_update_allows_changes_to_unanswered_questions(self):
        content = simple_content()
        content["survey"] = content["survey"][:1]
        code, out, err = self.run_cli("update-form", "aEmpty", "--content", self.content_file(content))
        self.assertEqual(code, 0, err)

    def test_update_backs_up_then_patches_and_deploys(self):
        content = simple_content()
        content["survey"].insert(1, {"type": "text", "name": "phone", "label": ["Телефон"]})
        before = self.fake.assets["aForm"]["version_id"]
        code, out, err = self.run_cli("update-form", "aForm", "--content", self.content_file(content), "--deploy")
        self.assertEqual(code, 0, err)
        [copy_dir] = self.backup_dirs("aForm")
        saved = json.loads((copy_dir / "asset.json").read_text())
        self.assertEqual(saved["version_id"], before, "the copy holds the form as it was before the change")
        form = self.fake.assets["aForm"]
        self.assertEqual(form["content"]["survey"][1]["name"], "phone")
        self.assertEqual(form["deployed_version_id"], form["version_id"])
        self.assertIn(str(copy_dir), out)

    def test_update_stops_when_backup_fails(self):
        content = copy.deepcopy(simple_content())
        self.fake.fail[("GET", "/api/v2/assets/aForm/versions/v1/")] = [500] * 4
        code, out, err = self.run_cli("update-form", "aForm", "--content", self.content_file(content))
        self.assertEqual(code, 2)
        self.assertEqual(self.fake.calls("PATCH"), [])

    # --- deploy / archive ---------------------------------------------------------------------------

    def test_deploy_first_time_and_redeploy(self):
        self.fake.add_form("aDraft", "Чернетка", deployed=False, shared={"kobo_edobro": FULL})
        code, out, err = self.run_cli("deploy", "aDraft")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.fake.calls("POST", "aDraft/deployment/")), 1)
        self.assertTrue(self.fake.assets["aDraft"]["has_deployment"])
        self.fake.assets["aDraft"]["version_id"] = "v9"
        self.fake.assets["aDraft"]["versions"]["v9"] = {"content": simple_content(), "deployed": False}
        code, out, err = self.run_cli("deploy", "aDraft")
        self.assertEqual(code, 0, err)
        [patch] = self.fake.calls("PATCH", "aDraft/deployment/")
        self.assertEqual(patch[2], {"active": True, "version_id": "v9"})
        self.assertEqual(len(self.backup_dirs("aDraft")), 2)

    def test_deploy_reminds_to_share(self):
        self.fake.add_form("aLonely", "Самотня", deployed=False)
        code, out, err = self.run_cli("deploy", "aLonely")
        self.assertEqual(code, 0, err)
        self.assertIn("не поділена", out)

    def test_archive_and_unarchive(self):
        code, out, err = self.run_cli("archive", "aForm")
        self.assertEqual(code, 0, err)
        self.assertFalse(self.fake.assets["aForm"]["active"])
        code, out, err = self.run_cli("unarchive", "aForm")
        self.assertEqual(code, 0, err)
        self.assertTrue(self.fake.assets["aForm"]["active"])


if __name__ == "__main__":
    unittest.main()
