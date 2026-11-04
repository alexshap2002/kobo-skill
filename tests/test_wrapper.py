from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import ROOT, SCRIPTS, KoboTestCase

WRAPPER = SCRIPTS / "kobo"
HOOK = ROOT / "plugins" / "kobo" / "hooks" / "run-hook.cmd"
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


def bash() -> str:
    # On Windows, plain "bash" may be the WSL launcher; Claude Code itself uses Git Bash.
    if sys.platform == "win32" and GIT_BASH.exists():
        return str(GIT_BASH)
    return shutil.which("bash") or "bash"


def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([bash(), *args], capture_output=True, text=True, encoding="utf-8",
                          env=env, timeout=60)


class WrapperTest(KoboTestCase):
    def test_wrapper_runs_cli(self):
        result = run(str(WRAPPER), "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check-sharing", result.stdout)

    def test_wrapper_explains_missing_python(self):
        result = run(str(WRAPPER), "forms", env={**os.environ, "PATH": str(self.tmp / "nothing")})
        self.assertEqual(result.returncode, 3)
        self.assertIn("Python", result.stderr)

    def test_session_hook_is_silent_without_setup(self):
        result = run(str(HOOK), "session-start")
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_session_hook_reports_unshared_forms(self):
        self.login()
        self.fake.add_form("aLonely", "Самотня")
        result = run(str(HOOK), "session-start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("aLonely", result.stdout)
        self.assertIn("Будь вільний", result.stdout)


if __name__ == "__main__":
    unittest.main()
