from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "kobo" / "skills" / "kobo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import kobo  # noqa: E402
from fake_kobo import OLENA, FakeKobo  # noqa: E402


class KoboTestCase(unittest.TestCase):
    """Each test gets a fresh fake Kobo, an empty home folder and an empty backup folder."""

    def setUp(self) -> None:
        self.fake = FakeKobo()
        self.addCleanup(self.fake.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home = self.tmp / "дім .kobo"
        self.backups = self.tmp / "Kobo-копії"
        env = mock.patch.dict(os.environ, {"KOBO_URL": self.fake.url, "KOBO_HOME": str(self.home),
                                           "KOBO_BACKUP_DIR": str(self.backups)})
        env.start()
        self.addCleanup(env.stop)
        sleep = mock.patch.object(kobo.time, "sleep", lambda s: None)
        sleep.start()
        self.addCleanup(sleep.stop)

    def run_cli(self, *argv: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(stdin)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kobo.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def login(self, token: str = OLENA) -> None:
        code, out, err = self.run_cli("setup", stdin=token + "\n")
        self.assertEqual(code, 0, out + err)

    def backup_dirs(self, uid: str) -> list[Path]:
        folders = list(self.backups.glob(f"*__{uid}"))
        return sorted(p for f in folders for p in f.iterdir() if p.is_dir()) if folders else []
