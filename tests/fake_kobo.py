"""A small in-memory KoboToolbox (kpi v2) served over local HTTP for tests."""

from __future__ import annotations

import copy
import io
import json
import re
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

OLENA = "a" * 40
PETRO = "b" * 40
MAIN = "c" * 40
TOKENS = {OLENA: "olena", PETRO: "petro", MAIN: "kobo_edobro"}

FULL = [
    "view_asset", "change_asset", "manage_asset", "view_submissions", "add_submissions",
    "change_submissions", "delete_submissions", "validate_submissions",
]
ASSIGNABLE = FULL[:3] + ["view_submissions", "partial_submissions"] + FULL[4:]


def simple_content() -> dict:
    return {
        "survey": [
            {"type": "text", "name": "name", "label": ["Ім'я"]},
            {"type": "select_one", "name": "city", "label": ["Місто"], "select_from_list_name": "cities"},
            {"type": "begin_repeat", "name": "kids", "label": ["Діти"]},
            {"type": "integer", "name": "age", "label": ["Вік"]},
            {"type": "end_repeat"},
        ],
        "choices": [
            {"list_name": "cities", "name": "kyiv", "label": ["Київ"]},
            {"list_name": "cities", "name": "lviv", "label": ["Львів"]},
        ],
        "settings": {},
        "translations": [None],
        "translated": ["label"],
    }


def submission(sid: int, **answers) -> dict:
    record = {"_id": sid, "_uuid": f"uuid-{sid}", "_submission_time": "2026-11-01T10:00:00",
              "_attachments": [], "_validation_status": {}}
    record.update(answers)
    return record


def fake_xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


class FakeKobo:
    def __init__(self) -> None:
        self.assets: dict[str, dict] = {}
        self.data: dict[str, list[dict]] = {}
        self.files: dict[str, bytes] = {}
        self.imports: dict[str, dict] = {}
        self.log: list[tuple[str, str, object]] = []
        self.fail: dict[tuple[str, str], list[int]] = {}  # statuses to answer before working
        self.max_page = 1000
        self._n = 0
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # keep test output quiet
                pass

            def _go(self):
                fake._handle(self)

            do_GET = do_POST = do_PATCH = do_DELETE = _go

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # --- fixtures -----------------------------------------------------------------------------------

    def add_form(self, uid: str, name: str = "Анкета", owner: str = "olena", content: dict | None = None,
                 deployed: bool = True, submissions: list[dict] | None = None, shared: dict | None = None) -> dict:
        content = copy.deepcopy(content or simple_content())
        asset = {
            "uid": uid, "name": name, "owner": owner, "content": content, "version_id": "v1",
            "deployed_version_id": "v1" if deployed else None, "has_deployment": deployed,
            "active": deployed,
            "versions": {"v1": {"content": copy.deepcopy(content), "deployed": deployed}},
            "perms": [(owner, p, f"p{uid}{i}") for i, p in enumerate(FULL)],
        }
        for user, perms in (shared or {}).items():
            for p in perms:
                asset["perms"].append((user, p, self._id("perm")))
        self.assets[uid] = asset
        self.data[uid] = list(submissions or [])
        return asset

    def perms_of(self, uid: str, user: str) -> set[str]:
        return {p for u, p, _ in self.assets[uid]["perms"] if u == user}

    def calls(self, method: str | None = None, contains: str = "") -> list[tuple[str, str, object]]:
        return [c for c in self.log if (method is None or c[0] == method) and contains in c[1]]

    # --- internals ----------------------------------------------------------------------------------

    def _id(self, prefix: str) -> str:
        with self._lock:
            self._n += 1
            return f"{prefix}{self._n}"

    def _asset_json(self, a: dict, detail: bool = True) -> dict:
        base = self.url
        status = "deployed" if a["active"] else ("archived" if a["has_deployment"] else "draft")
        deployed = [vid for vid, v in a["versions"].items() if v["deployed"]]
        out = {
            "url": f"{base}/api/v2/assets/{a['uid']}/", "uid": a["uid"], "name": a["name"],
            "owner__username": a["owner"], "asset_type": "survey", "version_id": a["version_id"],
            "deployed_version_id": a["deployed_version_id"], "has_deployment": a["has_deployment"],
            "deployment__active": a["active"], "deployment_status": status,
            "deployment__submission_count": len(self.data.get(a["uid"], [])),
            "permissions": [
                {"url": f"{base}/api/v2/assets/{a['uid']}/permission-assignments/{pid}/",
                 "user": f"{base}/api/v2/users/{u}/", "permission": f"{base}/api/v2/permissions/{p}/"}
                for u, p, pid in a["perms"]
            ],
        }
        if detail:
            out.update({
                "content": a["content"],
                "deployed_versions": {"count": len(deployed), "results": [
                    {"uid": vid, "url": f"{base}/api/v2/assets/{a['uid']}/versions/{vid}/",
                     "date_deployed": "2026-11-01T10:00:00Z"} for vid in reversed(deployed)]},
                "assignable_permissions": [{"url": f"{base}/api/v2/permissions/{p}/", "label": p}
                                           for p in ASSIGNABLE],
                "downloads": [{"format": "xls", "url": f"{base}/api/v2/assets/{a['uid']}.xls"},
                              {"format": "xml", "url": f"{base}/api/v2/assets/{a['uid']}.xml"}],
            })
        return out

    def _page(self, h, path: str, items: list, query: dict) -> None:
        limit = min(int(query.get("limit", ["100"])[0]), self.max_page)
        start = int(query.get("start", ["0"])[0])
        nxt = None
        if start + limit < len(items):
            q = {k: v[0] for k, v in query.items()}
            q.update(start=str(start + limit), limit=str(limit))
            nxt = f"{self.url}{path}?" + "&".join(f"{k}={v}" for k, v in q.items())
        self._send(h, 200, {"count": len(items), "next": nxt, "previous": None,
                            "results": items[start:start + limit]})

    def _send(self, h, status: int, body=None, raw: bytes | None = None, ctype: str = "application/json") -> None:
        payload = raw if raw is not None else (b"" if body is None else json.dumps(body).encode())
        h.send_response(status)
        h.send_header("Content-Type", ctype)
        h.send_header("Content-Length", str(len(payload)))
        h.end_headers()
        h.wfile.write(payload)

    def _handle(self, h) -> None:
        parts = urlsplit(h.path)
        path, query = parts.path, parse_qs(parts.query)
        length = int(h.headers.get("Content-Length") or 0)
        raw = h.rfile.read(length) if length else b""
        ctype = h.headers.get("Content-Type", "")
        body = json.loads(raw) if raw and ctype.startswith("application/json") else raw
        self.log.append((h.command, path, body))
        if self.fail.get((h.command, path)):
            return self._send(h, self.fail[(h.command, path)].pop(0), {"detail": "fail"})
        auth = h.headers.get("Authorization", "")
        user = TOKENS.get(auth[len("Token "):]) if auth.startswith("Token ") else None
        if user is None:
            return self._send(h, 401, {"detail": "Invalid token."})
        try:
            self._route(h, h.command, path, query, body, user)
        except KeyError:
            self._send(h, 404, {"detail": "Not found."})

    def _route(self, h, method, path, query, body, user) -> None:  # noqa: C901 — a router, flat on purpose
        if path == "/me/":
            return self._send(h, 200, {"username": user, "email": f"{user}@example.org"})
        m = re.fullmatch(r"/api/v2/users/(\w+)/", path)
        if m and method == "GET":
            if m.group(1) not in set(TOKENS.values()) | {"kobo_ymbefree"}:
                raise KeyError(path)
            return self._send(h, 200, {"username": m.group(1)})
        if path == "/api/v2/assets/" and method == "GET":
            mine = [self._asset_json(a, detail=False) for a in self.assets.values()
                    if a["owner"] == user or any(u == user for u, _, _ in a["perms"])]
            return self._page(h, path, mine, query)
        if path == "/api/v2/assets/" and method == "POST":
            uid = self._id("new")
            if body.get("clone_from"):
                content = copy.deepcopy(self.assets[body["clone_from"]]["content"])
            else:
                content = body["content"]
            self.add_form(uid, body.get("name", ""), owner=user, content=content, deployed=False)
            return self._send(h, 201, self._asset_json(self.assets[uid]))
        if path == "/api/v2/imports/" and method == "POST":
            iid = self._id("imp")
            uid = self._id("new")
            self.add_form(uid, "Імпортована", owner=user, deployed=False)
            self.imports[iid] = {"library": re.search(rb'name="library"\r\n\r\n(\w+)', body).group(1).decode(),
                                 "asset": uid, "polls": 0}
            return self._send(h, 201, {"uid": iid})
        m = re.fullmatch(r"/api/v2/imports/(\w+)/", path)
        if m:
            imp = self.imports[m.group(1)]
            imp["polls"] += 1
            if imp["polls"] < 2:
                return self._send(h, 200, {"status": "processing", "messages": {}})
            return self._send(h, 200, {"status": "complete",
                                       "messages": {"created": [{"uid": imp["asset"], "kind": "asset"}]}})
        m = re.fullmatch(r"/api/v2/assets/(\w+)\.xls", path)
        if m:
            self.assets[m.group(1)]
            return self._send(h, 200, raw=fake_xlsx(), ctype="application/vnd.ms-excel")
        m = re.fullmatch(r"/api/v2/assets/(\w+)/(.*)", path)
        if not m:
            raise KeyError(path)
        uid, rest = m.groups()
        a = self.assets[uid]
        if rest == "" and method == "GET":
            return self._send(h, 200, self._asset_json(a))
        if rest == "" and method == "PATCH":
            if "content" in body:
                a["content"] = body["content"]
                vid = self._id("ver")  # not "v1": that is every form's first version
                a["version_id"] = vid
                a["versions"][vid] = {"content": copy.deepcopy(body["content"]), "deployed": False}
            if "name" in body:
                a["name"] = body["name"]
            return self._send(h, 200, self._asset_json(a))
        if rest == "" and method == "DELETE":
            del self.assets[uid]
            return self._send(h, 204)
        m = re.fullmatch(r"versions/(\w+)/", rest)
        if m and method == "GET":
            v = a["versions"][m.group(1)]
            return self._send(h, 200, {"uid": m.group(1), "content": v["content"],
                                       "date_deployed": "2026-11-01T10:00:00Z"})
        if rest == "deployment/":
            if method == "POST":
                if a["has_deployment"]:
                    return self._send(h, 400, {"detail": "already deployed"})
                self._deploy(a, a["version_id"])
                return self._send(h, 200, {"active": True})
            if method == "PATCH":
                if body.get("version_id"):
                    self._deploy(a, body["version_id"])
                if "active" in body:
                    a["active"] = bool(body["active"])
                return self._send(h, 200, {"active": a["active"]})
        if rest.startswith("data/") and not a["has_deployment"]:
            return self._send(h, 400, {"detail": "The specified asset has not been deployed"})  # real kpi
        if rest == "data/" and method == "GET":
            return self._page(h, f"/api/v2/assets/{uid}/data/", self.data[uid], query)
        if rest == "data/bulk/" and method == "PATCH":
            p = body["payload"]
            for record in self.data[uid]:
                if record["_id"] in p["submission_ids"]:
                    record.update(p["data"])
            return self._send(h, 200, {"count": len(p["submission_ids"])})
        if rest == "data/validation_statuses/" and method == "PATCH":
            p = body["payload"]
            for record in self.data[uid]:
                if record["_id"] in p["submission_ids"]:
                    record["_validation_status"] = {"uid": p["validation_status.uid"]}
            return self._send(h, 200, {"detail": "ok"})
        m = re.fullmatch(r"data/(\d+)/", rest)
        if m and method == "DELETE":
            before = len(self.data[uid])
            self.data[uid] = [r for r in self.data[uid] if r["_id"] != int(m.group(1))]
            return self._send(h, 204 if len(self.data[uid]) < before else 404)
        m = re.fullmatch(r"data/(\d+)/attachments/(\w+)/", rest)
        if m and method == "GET":
            return self._send(h, 200, raw=self.files[m.group(2)], ctype="image/jpeg")
        if rest == "permission-assignments/" and method == "GET":
            return self._send(h, 200, self._asset_json(a, detail=False)["permissions"])
        if rest == "permission-assignments/" and method == "POST":
            who = body["user"].rstrip("/").rsplit("/", 1)[-1]
            perm = body["permission"].rstrip("/").rsplit("/", 1)[-1]
            if perm not in ASSIGNABLE:
                return self._send(h, 400, {"detail": "bad permission"})
            a["perms"].append((who, perm, self._id("perm")))
            return self._send(h, 201, {"user": body["user"], "permission": body["permission"]})
        m = re.fullmatch(r"permission-assignments/(\w+)/", rest)
        if m and method == "DELETE":
            a["perms"] = [x for x in a["perms"] if x[2] != m.group(1)]
            return self._send(h, 204)
        raise KeyError(rest)

    def _deploy(self, a: dict, vid: str) -> None:
        a["versions"][vid]["deployed"] = True
        a["deployed_version_id"] = vid
        a["has_deployment"] = True
        a["active"] = True
