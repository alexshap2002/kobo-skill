from __future__ import annotations

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
            for old in ("$KOBO", "scripts/kobo", "~/.kobo", "Kobo-копії"):
                self.assertNotIn(old, text, f"{doc.name} still mentions {old}")

    def test_key_lives_in_the_work_folder_file(self):
        self.assertIn("kobo-ключ.txt", read(SKILL / "SKILL.md"))


if __name__ == "__main__":
    unittest.main()
