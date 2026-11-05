"""Runs the page helper from references/api.md in Node against the fake Kobo, exactly as the doc gives it."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from fake_kobo import FULL, MAIN, OLENA, FakeKobo

API_DOC = Path(__file__).resolve().parents[1] / "plugins/kobo/skills/kobo/references/api.md"


def helper() -> str:
    blocks = re.findall(r"```js\n(.*?)```", API_DOC.read_text(encoding="utf-8"), re.S)
    return blocks[0]


@unittest.skipUnless(shutil.which("node"), "needs Node to run the browser helper")
class PageHelperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeKobo()
        self.addCleanup(self.fake.close)

    def run_js(self, body: str):
        """body runs in an async function after the helper; its return value comes back as JSON."""
        script = (f"globalThis.window = globalThis;\nglobalThis.location = {{origin: {json.dumps(self.fake.url)}}};\n"
                  f"{helper()}\n"
                  f"(async () => {{ {body} }})().then(r => console.log(JSON.stringify(r)));")
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_connect_accepts_own_key_only(self):
        result = self.run_js(f"""
            const bad = await kobo.connect('x'.repeat(40));
            const main = await kobo.connect({json.dumps(MAIN)});
            const unset = await kobo('GET', '/me/');
            const own = await kobo.connect(' {OLENA}\\n');
            const me = await kobo('GET', '/me/');
            return {{bad, main, unset, own, me}};""")
        self.assertEqual(result["bad"], {"ok": False, "why": "ключ не підійшов", "status": 401})
        self.assertEqual(result["main"], {"ok": False, "why": "головний акаунт організації"})
        self.assertEqual(result["unset"]["status"], 0, "a refused key is not kept")
        self.assertEqual(result["own"], {"ok": True, "username": "olena"})
        self.assertEqual(result["me"]["data"]["username"], "olena")

    def test_key_never_goes_to_another_server(self):
        result = self.run_js(f"""
            await kobo.connect({json.dumps(OLENA)});
            return await kobo('GET', 'https://example.org/steal');""")
        self.assertEqual(result["status"], 0)
        self.assertNotIn("/steal", [path for _, path, _ in self.fake.log])

    def test_all_follows_pages(self):
        self.fake.max_page = 2
        for i in range(5):
            self.fake.add_form(f"a{i}", f"Форма {i}")
        result = self.run_js(f"""
            await kobo.connect({json.dumps(OLENA)});
            const r = await kobo.all('/api/v2/assets/?q=asset_type:survey&limit=2');
            return r.data.map(a => a.uid);""")
        self.assertEqual(sorted(result), [f"a{i}" for i in range(5)])

    def test_share_adds_missing_permissions_one_by_one(self):
        self.fake.add_form("aF", "Форма", shared={"kobo_ymbefree": ["view_asset"], "petro": ["view_asset"]})
        result = self.run_js(f"""
            await kobo.connect({json.dumps(OLENA)});
            return await kobo.share('aF', 'kobo_ymbefree');""")
        self.assertEqual(result, {"ok": True, "missing": []})
        self.assertEqual(self.fake.perms_of("aF", "kobo_ymbefree"), set(FULL))
        self.assertEqual(self.fake.perms_of("aF", "petro"), {"view_asset"}, "nobody else's access changes")
        posts = self.fake.calls("POST", "permission-assignments")
        self.assertEqual(len(posts), len(FULL) - 1)
        self.assertFalse(any("bulk" in path for _, path, _ in posts))
        self.assertEqual(self.fake.calls("DELETE"), [])

    def test_unshared_lists_own_forms_without_full_org_access(self):
        self.fake.add_form("aOk", "Поділена", shared={"kobo_edobro": FULL})
        self.fake.add_form("aNone", "Нічия")
        self.fake.add_form("aHalf", "Половинчаста", shared={"kobo_ymbefree": ["view_asset"]})
        self.fake.add_form("aMixed", "Змішана", shared={"kobo_edobro": FULL, "kobo_ymbefree": ["view_asset"]})
        self.fake.add_form("aForeign", "Чужа", owner="petro", shared={"olena": ["view_asset"]})
        result = self.run_js(f"""
            await kobo.connect({json.dumps(OLENA)});
            return await kobo.unshared();""")
        self.assertEqual(result["status"], 200)
        self.assertEqual({f["uid"]: (f["kobo_ymbefree"], f["kobo_edobro"]) for f in result["data"]}, {
            "aNone": ("none", "none"),
            "aHalf": ("partial", "none"),
            "aMixed": ("partial", "full"),
        })
        self.assertEqual({f["name"] for f in result["data"]}, {"Нічия", "Половинчаста", "Змішана"})

    def test_deploy_first_time_then_new_version(self):
        self.fake.add_form("aD", "Чернетка", deployed=False)
        self.run_js(f"""
            await kobo.connect({json.dumps(OLENA)});
            await kobo.deploy('aD');
            await kobo('PATCH', '/api/v2/assets/aD/', {{content: {{survey: [], choices: [], settings: {{}}}}}});
            return await kobo.deploy('aD');""")
        first, second = self.fake.calls(contains="/deployment/")
        self.assertEqual((first[0], first[2]), ("POST", {"active": True}))
        self.assertEqual(second[0], "PATCH")
        self.assertEqual(second[2]["version_id"], self.fake.assets["aD"]["deployed_version_id"])
        self.assertNotEqual(second[2]["version_id"], "v1")


if __name__ == "__main__":
    unittest.main()
