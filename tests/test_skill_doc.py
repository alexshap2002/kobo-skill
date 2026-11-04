from __future__ import annotations

import re
import unittest

from helpers import SCRIPTS, kobo

SKILL = SCRIPTS.parent


class SkillDocTest(unittest.TestCase):
    def test_skill_names_only_real_commands(self):
        commands = set(kobo.parser()._subparsers._group_actions[0].choices)  # type: ignore[union-attr]
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        text = skill + "".join(p.read_text(encoding="utf-8") for p in SKILL.glob("references/*.md"))
        named = set(re.findall(r'"\$KOBO" ([a-z][a-z-]+)', text)) | set(re.findall(r"\| `([a-z][a-z-]+)[ `]", skill))
        self.assertTrue(named)
        self.assertEqual(named - commands, set())
        self.assertEqual(commands - set(re.findall(r"[a-z][a-z-]+", text)), set(), "every command is documented")

    def test_frontmatter(self):
        m = re.match(r"---\nname: kobo\ndescription: (.+)\n---\n", (SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIsNotNone(m)
        self.assertLessEqual(len(m.group(1)), 1024)


if __name__ == "__main__":
    unittest.main()
