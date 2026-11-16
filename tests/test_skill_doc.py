from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "plugins/kobo/skills/kobo"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SkillDocTest(unittest.TestCase):
    def test_frontmatter(self):
        m = re.match(r"---\nname: kobo\ndescription: (.+)\n---\n", read(SKILL / "SKILL.md"))
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1)), 1024)

    def test_references_exist_and_are_named(self):
        named = set(re.findall(r"`references/([\w-]+\.md)`", read(SKILL / "SKILL.md")))
        present = {p.name for p in (SKILL / "references").glob("*.md")}
        self.assertEqual(named, present)

    def test_no_traces_of_the_old_helper_program(self):
        for doc in [SKILL / "SKILL.md", *(SKILL / "references").glob("*.md")]:
            text = read(doc)
            for old in ("$KOBO", "scripts/kobo", "~/.kobo"):
                self.assertNotIn(old, text, f"{doc.name} still mentions {old}")

    def test_key_lives_in_the_work_folder_file(self):
        self.assertIn("kobo-ключ.txt", read(SKILL / "SKILL.md"))

    def test_gold_standard_is_valid_form_content(self):
        text = read(SKILL / "references/standard.md")
        self.assertIn("2026-06-26-v3", text, "the standard's version is named")
        blocks = re.findall(r"```json\n(.*?)```", text, re.S)
        self.assertEqual(len(blocks), 1)
        content = json.loads(blocks[0])
        survey, choices = content["survey"], content["choices"]
        self.assertEqual(len(survey), 59)
        names = [q["name"] for q in survey]
        self.assertEqual(len(names), len(set(names)), "technical names are unique")
        lists = {c["list_name"] for c in choices}
        for q in survey:
            if q["type"].startswith("select"):
                self.assertIn(q["select_from_list_name"], lists, q["name"])
            for col in ("label", "hint", "constraint_message"):
                if col in q:
                    self.assertIn(col, content["translated"], q["name"])
                    self.assertEqual(len(q[col]), len(content["translations"]), q["name"])
            if "choice_filter" in q:
                column = q["choice_filter"].split("=")[0].strip()
                self.assertTrue(any(column in c for c in choices if c["list_name"] == q["select_from_list_name"]),
                                q["name"])
        for c in choices:
            self.assertEqual(len(c["label"]), len(content["translations"]), c["name"])

    def test_every_form_gets_the_same_consent_question(self):
        row = ('{"type": "acknowledge", "name": "consent", "label": ["Натискаючи тут, я даю згоду на обробку моїх '
               'персональних даних"], "required": true}')
        json.loads(row)
        self.assertIn(row, read(SKILL / "SKILL.md"))
        self.assertIn(row, read(SKILL / "references/forms.md"), "the example form uses the same question")

    def test_a_form_without_project_gets_one_fixed_name(self):
        self.assertIn("рівно «Без проєкту»", read(SKILL / "SKILL.md"))


if __name__ == "__main__":
    unittest.main()
