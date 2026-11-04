#!/usr/bin/env python3
"""Kobo helper for employees of «Будь вільний» and «Є добро».

Every change to Kobo goes through this script so the organisation's rules hold in code:
a local copy before any change, and every form shared with an organisation main account.
Python 3.9+ standard library only (Mac and Windows).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from typing import Any, Iterator

SERVER = "https://eu.kobotoolbox.org"
ORGS = {"bud-vilnyi": ("Будь вільний", "kobo_ymbefree"), "ye-dobro": ("Є добро", "kobo_edobro")}
MAIN_ACCOUNTS = {user for _, user in ORGS.values()}
ADMIN = "Олександр Шаповалов (Telegram @olexandr_shapovalov)"
RETRY_DELAYS = (2, 5, 15)
RETRY_STATUS = {429, 500, 502, 503, 504}
KEEP_COPIES = 5


class KoboError(Exception):
    """Something the employee should read: plain Ukrainian, no traceback."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# --- places on this computer -------------------------------------------------------------------------


def server() -> str:
    return os.environ.get("KOBO_URL", SERVER).rstrip("/")


def home() -> Path:
    return Path(os.environ.get("KOBO_HOME") or Path.home() / ".kobo")


def backup_root() -> Path:
    return Path(os.environ.get("KOBO_BACKUP_DIR") or Path.home() / "Kobo-копії")


def save_token(token: str) -> None:
    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    tmp = folder / "token.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, folder / "token")


def load_token() -> str:
    try:
        token = (home() / "token").read_text().strip()
    except OSError:
        token = ""
    if not token:
        raise KoboError(
            "Kobo ще не налаштовано на цьому комп'ютері. Попросіть працівника вставити в чат "
            "свій API-ключ з eu.kobotoolbox.org (Account Settings → Security → API Key → Display) "
            "і збережіть його командою setup."
        )
    return token


def load_state() -> dict:
    try:
        state = json.loads((home() / "state.json").read_text())
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def save_state(state: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    tmp = home() / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, home() / "state.json")


# --- HTTP ------------------------------------------------------------------------------------------------


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if sys.platform == "darwin" and not ctx.cert_store_stats().get("x509_ca"):
        # python.org installers ship without certificates; borrow the system ones.
        pem = subprocess.run(
            ["/usr/bin/security", "find-certificate", "-a", "-p",
             "/System/Library/Keychains/SystemRootCertificates.keychain"],
            capture_output=True, text=True, check=False,
        ).stdout
        if pem:
            ctx.load_verify_locations(cadata=pem)
    return ctx


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme, (parts.hostname or "").lower(), parts.port or {"http": 80, "https": 443}.get(parts.scheme)


def _kobo_says(raw: bytes) -> str:
    try:
        body = json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")[:300]
    if isinstance(body, dict) and len(body) == 1:
        body = next(iter(body.values()))
    return (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))[:300]


class Kobo:
    """Minimal kpi v2 client. The key is sent only to the configured server."""

    def __init__(self, base: str, token: str, timeout: float = 60, retry: bool = True) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retry = retry
        self._ctx = _ssl_context() if self.base.startswith("https:") else None

    def url(self, path: str) -> str:
        url = urllib.parse.urljoin(self.base + "/", path)
        parts = urllib.parse.urlsplit(url)
        if parts.username or parts.password or _origin(url) != _origin(self.base):
            raise KoboError(f"Відмовляюсь надсилати ключ на інший сайт: {parts.hostname}. Працюю лише з {self.base}.")
        return url

    def request(self, method: str, path: str, body: Any = None, *, data: bytes | None = None,
                content_type: str = "application/json", params: dict | None = None,
                ok: tuple[int, ...] = (200, 201, 202, 204), raw: bool = False) -> Any:
        url = self.url(path)
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        if body is not None:
            data = json.dumps(body).encode()
        delays = RETRY_DELAYS if self.retry else ()
        status, payload = 0, b""
        for attempt in range(len(delays) + 1):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_unredirected_header("Authorization", f"Token {self.token}")
            req.add_header("Accept", "application/json")
            if data is not None:
                req.add_header("Content-Type", content_type)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as resp:
                    status, payload = resp.status, resp.read()
            except urllib.error.HTTPError as e:
                status, payload = e.code, e.read()
            except (urllib.error.URLError, OSError) as e:
                if attempt < len(delays):
                    time.sleep(delays[attempt])
                    continue
                if isinstance(getattr(e, "reason", None), ssl.SSLError):
                    raise KoboError("Не вдалося встановити захищене з'єднання з Kobo (сертифікати). "
                                    f"Зверніться до адміністратора: {ADMIN}.") from None
                raise KoboError(f"Немає зв'язку з {urllib.parse.urlsplit(self.base).hostname}. "
                                "Перевірте інтернет і спробуйте ще раз.") from None
            if status in RETRY_STATUS and attempt < len(delays):
                time.sleep(delays[attempt])
                continue
            break
        if status in ok:
            if raw:
                return payload
            return json.loads(payload) if payload.strip() else None
        if status in RETRY_STATUS:
            raise KoboError("Сервер Kobo зараз не відповідає. Спробуйте за кілька хвилин.", status)
        if status == 401:
            raise KoboError("Kobo не прийняв ключ. Можливо, його змінили: попросіть працівника дати новий "
                            "API-ключ і збережіть його командою setup.", status)
        if status == 403:
            raise KoboError("Kobo каже, що у вашого акаунта немає на це прав.", status)
        if status == 404:
            raise KoboError("Kobo не знайшов цю форму чи запис. Можливо, його вже видалили або код неправильний.",
                            status)
        raise KoboError(f"Kobo відхилив запит ({status}): {_kobo_says(payload)}", status)

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> Any:
        return self.request("POST", path, body, **kw)

    def patch(self, path: str, body: Any = None, **kw: Any) -> Any:
        return self.request("PATCH", path, body, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.request("DELETE", path, **kw)

    def pages(self, path: str, params: dict | None = None) -> Iterator[dict]:
        url: str | None = path
        while url:
            page = self.get(url, params=params)
            params = None
            yield from page.get("results") or []
            url = page.get("next")


def client() -> Kobo:
    return Kobo(server(), load_token())


def account(kobo: Kobo) -> str:
    """The employee's username, remembered at setup."""
    username = load_state().get("username") or kobo.get("/me/").get("username")
    if username in MAIN_ACCOUNTS:
        raise KoboError(f"Цей ключ від головного акаунта {username}. З ним плагін не працює. {ADMIN}.")
    return username


# --- forms and sharing -----------------------------------------------------------------------------

FULL = ("view_asset", "change_asset", "manage_asset", "view_submissions", "add_submissions",
        "change_submissions", "delete_submissions", "validate_submissions")
ROLES = {
    "view": ("view_asset", "view_submissions"),
    "edit": ("view_asset", "change_asset", "view_submissions", "add_submissions", "change_submissions",
             "validate_submissions"),
    "full": FULL,
}
STATUS_UA = {"deployed": "розгорнута", "draft": "чернетка, ще не розгорнута", "archived": "архівна"}
SHARING_UA = {"full": "повні права", "partial": "не всі права", "none": "не поділена"}
SHARING_RULE = (
    "Правило організації: кожна форма, також тестова чи навчальна, має бути поділена з повними правами "
    "з «Будь вільний» (kobo_ymbefree) або «Є добро» (kobo_edobro), інакше її немає в архіві й Google "
    "Таблицях. Відмовитись не можна. Запитайте працівника, для якої організації кожна форма («Будь вільний», "
    "«Є добро» чи обидві), і поділіться: kobo share <uid> --org bud-vilnyi|ye-dobro|both. "
    "Де права неповні, запропонуйте доповнити їх тією самою командою."
)
DAILY_HEADER = "Плагін Kobo, щоденна перевірка: скажіть про це працівнику на початку розмови."


def _last(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def grants(asset: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for p in asset.get("permissions") or []:
        out.setdefault(_last(p["user"]), set()).add(_last(p["permission"]))
    return out


def sharing(asset: dict) -> dict[str, str]:
    have = grants(asset)
    return {org: "full" if set(FULL) <= have.get(user, set()) else "partial" if have.get(user) else "none"
            for org, (_, user) in ORGS.items()}


def list_forms(kobo: Kobo) -> list[dict]:
    forms = []
    for a in kobo.pages("/api/v2/assets/", {"q": "asset_type:survey", "limit": 300}):
        if a.get("asset_type", "survey") != "survey":
            continue
        if a.get("permissions") is None:
            a = kobo.get(f"/api/v2/assets/{a['uid']}/")
        forms.append(a)
    return forms


def describe(asset: dict, me: str) -> dict:
    return {"uid": asset["uid"], "name": asset.get("name") or "", "owner": asset.get("owner__username"),
            "mine": asset.get("owner__username") == me, "status": asset.get("deployment_status"),
            "submissions": asset.get("deployment__submission_count") or 0, "sharing": sharing(asset)}


def needs_sharing(form: dict) -> bool:
    states = form["sharing"].values()
    return "full" not in states or "partial" in states


def sharing_problems(kobo: Kobo) -> tuple[str, list[dict]]:
    me = account(kobo)
    return me, [f for f in (describe(a, me) for a in list_forms(kobo)) if f["mine"] and needs_sharing(f)]


def problem_text(problems: list[dict]) -> str:
    lines = ["Ці форми працівника ще не поділені з організацією як слід:"]
    for f in problems:
        partial = [f"«{ORGS[o][0]}»: не всі права" for o, s in f["sharing"].items() if s == "partial"]
        what = "; ".join(partial) if partial else "не поділена з жодною організацією"
        lines.append(f"• «{f['name']}» ({f['uid']}) — {what}")
    return "\n".join(lines + [SHARING_RULE])


def grant(kobo: Kobo, uid: str, user: str, perms: tuple[str, ...]) -> None:
    """Add the missing permissions one at a time; never touches anyone else's access."""
    asset = kobo.get(f"/api/v2/assets/{uid}/")
    assignable = {_last(p["url"]) for p in asset.get("assignable_permissions") or []} or set(perms)
    wanted = [p for p in perms if p in assignable]
    have = grants(asset).get(user, set())
    for perm in wanted:
        if perm not in have:
            # 400 can mean "already implied by another permission"; the re-read below decides.
            kobo.post(f"/api/v2/assets/{uid}/permission-assignments/",
                      {"user": f"{kobo.base}/api/v2/users/{user}/",
                       "permission": f"{kobo.base}/api/v2/permissions/{perm}/"}, ok=(200, 201, 400))
    now = grants(kobo.get(f"/api/v2/assets/{uid}/")).get(user, set())
    missing = [p for p in wanted if p not in now]
    if missing:
        raise KoboError(f"Kobo не видав акаунту {user} права {', '.join(missing)} на форму {uid}. "
                        f"Спробуйте ще раз; якщо повториться, зверніться до адміністратора: {ADMIN}.")


def org_keys(org: str) -> list[str]:
    return list(ORGS) if org == "both" else [org]


def share_with_orgs(kobo: Kobo, uid: str, org: str) -> str:
    keys = org_keys(org)
    for key in keys:
        grant(kobo, uid, ORGS[key][1], FULL)
    return " і ".join(f"«{ORGS[k][0]}» ({ORGS[k][1]})" for k in keys)


def deploy(kobo: Kobo, uid: str, active: bool = True) -> None:
    """Deploy the current version: first time POST, afterwards PATCH with the version."""
    asset = kobo.get(f"/api/v2/assets/{uid}/")
    if asset.get("has_deployment"):
        kobo.patch(f"/api/v2/assets/{uid}/deployment/", {"active": active, "version_id": asset["version_id"]})
    else:
        kobo.post(f"/api/v2/assets/{uid}/deployment/", {"active": True})


def daily_check() -> int:
    today = time.strftime("%Y-%m-%d")
    if load_state().get("sharing_ok_on") == today:
        return 0
    try:
        _, problems = sharing_problems(Kobo(server(), load_token(), timeout=15, retry=False))
    except KoboError:
        return 0  # not set up yet, or Kobo unreachable: stay quiet and try next session
    if problems:
        print(DAILY_HEADER + "\n" + problem_text(problems))
    else:
        state = load_state()
        state["sharing_ok_on"] = today
        save_state(state)
    return 0


# --- Excel without dependencies ----------------------------------------------------------------------

_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col(n: int) -> str:
    name = ""
    while n:
        n, r = divmod(n - 1, 26)
        name = chr(65 + r) + name
    return name


def write_xlsx(path: Path, sheets: list[tuple[str, list[list[Any]]]]) -> None:
    """A plain .xlsx (inline strings, no styles) that Excel, LibreOffice and Google Sheets open."""
    def cell(ref: str, value: Any) -> str:
        if isinstance(value, bool) or value is None:
            value = "" if value is None else str(value)
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        text = escape(_BAD_XML.sub("", str(value)))[:32000]
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'

    used: set[str] = set()
    titles = []
    for name, _ in sheets:
        title = re.sub(r"[\[\]:*?/\\]", "_", name)[:31] or "Аркуш"
        while title in used:
            title = title[:28] + f"_{len(used)}"
        used.add(title)
        titles.append(title)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      for i in range(1, len(sheets) + 1)) + "</Types>"))
        z.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"))
        z.writestr("xl/workbook.xml", (
            '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{escape(t, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>' for i, t in enumerate(titles, 1))
            + "</sheets></workbook>"))
        z.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                      for i in range(1, len(sheets) + 1)) + "</Relationships>"))
        for i, (_, rows) in enumerate(sheets, 1):
            body = "".join(
                f'<row r="{r}">' + "".join(cell(f"{_col(c)}{r}", v) for c, v in enumerate(row, 1)) + "</row>"
                for r, row in enumerate(rows, 1))
            z.writestr(f"xl/worksheets/sheet{i}.xml", (
                '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{body}</sheetData></worksheet>"))


# --- answers as human tables -------------------------------------------------------------------------

SYSTEM_COLUMNS = {"_id": "ID запису", "_submission_time": "Час подання", "_validation_status": "Статус перевірки",
                  "_submitted_by": "Хто подав"}
HIDDEN = {"_uuid", "_attachments", "_status", "_geolocation", "_tags", "_notes", "_xform_id_string", "_xform_id",
          "__version__", "_version_", "_bamboo_dataset_id", "formhub/uuid", "meta/instanceID", "meta/rootUuid",
          "meta/deprecatedID", "meta/instanceName", "_media_count", "_media_all_received", "_total_media",
          "_supplementalDetails"}
NUMERIC = {"integer", "decimal", "range"}


def _label(row: dict) -> str:
    label = row.get("label")
    if isinstance(label, list):
        label = next((x for x in label if x), "")
    return label or ""


def form_dictionary(content: dict) -> dict:
    """name -> (label, type, choices) from kpi content; names are unique within a form."""
    choices: dict[str, dict[str, str]] = {}
    for c in content.get("choices") or []:
        choices.setdefault(c.get("list_name"), {})[str(c.get("name"))] = _label(c) or str(c.get("name"))
    out = {}
    for row in content.get("survey") or []:
        name = row.get("name") or row.get("$autoname")
        if name:
            kind = str(row.get("type", "")).split(" ")[0]
            out[name] = (_label(row) or name, kind, choices.get(row.get("select_from_list_name"), {}))
    return out


def answer_tables(records: list[dict], content: dict) -> list[tuple[str, list[list[Any]]]]:
    """One sheet for the answers and one per repeat group, with labels instead of codes."""
    words = form_dictionary(content)
    order = {name: i for i, name in enumerate(words)}
    sheets: dict[str, list[dict]] = {"": []}

    def walk(record: dict, sheet: str, parent: Any) -> None:
        row: dict = {} if parent is None else {"_parent": parent}
        for key, value in record.items():
            if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                for item in value:
                    walk(item, key, record.get("_id", parent))
            elif key not in HIDDEN:
                row[key] = value
        sheets.setdefault(sheet, []).append(row)

    for record in records:
        walk(record, "", None)

    def show(key: str, value: Any) -> Any:
        if key == "_validation_status":
            return (value or {}).get("label", "") if isinstance(value, dict) else value
        label, kind, options = words.get(key.rsplit("/", 1)[-1], ("", "", {}))
        if kind == "select_one":
            return options.get(str(value), value)
        if kind == "select_multiple" and isinstance(value, str):
            return "; ".join(options.get(v, v) for v in value.split())
        if kind in NUMERIC and isinstance(value, str):
            try:
                return int(value) if re.fullmatch(r"-?\d+", value) else float(value)
            except ValueError:
                return value
        return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value

    result = []
    for sheet, rows in sheets.items():
        if sheet and not rows:
            continue
        keys: list[str] = []
        for row in rows:
            keys += [k for k in row if k not in keys]
        keys.sort(key=lambda k: (k not in ("_parent", "_id"), k.startswith("_"),
                                 order.get(k.rsplit("/", 1)[-1], len(order))))
        header = [("ID запису (батьківський)" if k == "_parent" else SYSTEM_COLUMNS.get(k)
                   or words.get(k.rsplit("/", 1)[-1], (k,))[0]) for k in keys]
        title = "Відповіді" if not sheet else words.get(sheet.rsplit("/", 1)[-1], (sheet,))[0]
        result.append((title, [header] + [[show(k, row.get(k, "")) for k in keys] for row in rows]))
    return result


# --- local copies ------------------------------------------------------------------------------------

STAMP = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d+)?")


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(" .")[:60].strip(" .") or "форма"


def copies(uid: str) -> list[Path]:
    """Finished copies of one form, newest first."""
    root = backup_root()
    folders = list(root.glob(f"*__{uid}")) if root.is_dir() else []
    found = [p for f in folders for p in f.iterdir() if p.is_dir() and STAMP.fullmatch(p.name)]
    return sorted(found, key=lambda p: p.name, reverse=True)


def deployed_versions(kobo: Kobo, asset: dict) -> list[dict]:
    """Deployed versions, oldest first. Paged only when the asset's own list is truncated."""
    listing = asset.get("deployed_versions") or {}
    items = listing.get("results") or []
    if listing.get("count") != len(items):
        items = list(kobo.pages(f"/api/v2/assets/{asset['uid']}/versions/", {"limit": 1000}))
    items = [v for v in items if v.get("date_deployed") and re.fullmatch(r"\w+", str(v.get("uid")))]
    return sorted(items, key=lambda v: (str(v["date_deployed"]), v["uid"]))


def xlsform_url(asset: dict) -> str | None:
    for d in asset.get("downloads") or []:
        if str(d.get("format", "")).lower() in ("xls", "xlsx") and d.get("url"):
            return d["url"]
    return None


def fetch_answers(kobo: Kobo, uid: str) -> list[dict]:
    return list(kobo.pages(f"/api/v2/assets/{uid}/data/", {"limit": 1000}))


def make_backup(kobo: Kobo, uid: str, reason: str) -> Path:
    """Copy one form (description, versions, all answers; never photos) and keep the newest copies."""
    asset = kobo.get(f"/api/v2/assets/{uid}/")
    previous = copies(uid)
    known: dict[str, dict] = {}
    if previous:
        try:
            known = {v["uid"]: v for v in json.loads((previous[0] / "versions.json").read_text(encoding="utf-8"))}
        except (OSError, ValueError, KeyError, TypeError):
            known = {}
    versions = []
    for v in deployed_versions(kobo, asset):
        if v["uid"] not in known:
            known[v["uid"]] = {"uid": v["uid"], "date_deployed": v["date_deployed"],
                               "content": kobo.get(f"/api/v2/assets/{uid}/versions/{v['uid']}/").get("content")}
        versions.append(known[v["uid"]])
    answers = fetch_answers(kobo, uid)
    note = ""
    xls = None
    try:
        url = xlsform_url(asset)
        xls = kobo.get(url, raw=True) if url else None
    except KoboError:
        pass
    if xls is None:
        note = "\nФайл form.xlsx Kobo не віддав; повний опис форми є в asset.json і versions.json."

    folder = previous[0].parent if previous else backup_root() / f"{safe_name(asset.get('name') or '')}__{uid}"
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    final, n = folder / stamp, 1
    while final.exists():
        n += 1
        final = folder / f"{stamp}-{n:02d}"
    tmp = folder / f".unfinished-{final.name}"
    tmp.mkdir(parents=True)
    content = asset.get("content") or {}
    (tmp / "asset.json").write_text(json.dumps(asset, ensure_ascii=False, indent=1), encoding="utf-8")
    (tmp / "versions.json").write_text(json.dumps(versions, ensure_ascii=False, indent=1), encoding="utf-8")
    (tmp / "submissions.json").write_text(json.dumps(answers, ensure_ascii=False, indent=1), encoding="utf-8")
    if xls is not None:
        (tmp / "form.xlsx").write_bytes(xls)
    write_xlsx(tmp / "submissions.xlsx", answer_tables(answers, content))
    (tmp / "ПРО_КОПІЮ.txt").write_text(
        f"Копія форми «{asset.get('name')}» ({uid}) з eu.kobotoolbox.org\n"
        f"Зроблено: {time.strftime('%Y-%m-%d %H:%M:%S')} — {reason}\n"
        f"Відповідей: {len(answers)}. Розгорнутих версій форми: {len(versions)}.{note}\n\n"
        "Що тут є:\n"
        "- submissions.xlsx — усі відповіді для перегляду в Excel;\n"
        "- submissions.json — усі відповіді (для відновлення);\n"
        "- form.xlsx — форма (XLSForm) на момент копії;\n"
        "- asset.json, versions.json — повний опис форми й усі її розгорнуті версії.\n"
        "Фото й файли до копії не входять.\n\n"
        "Повернути форму до цієї копії: попросіть Claude «поверни форму до копії».\n"
        f"Повернути відповіді: адміністратор {ADMIN}.\n", encoding="utf-8")
    os.replace(tmp, final)
    for old in copies(uid)[KEEP_COPIES:]:
        _remove_tree(old)
    return final


def _remove_tree(path: Path) -> None:
    for p in sorted(path.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        p.rmdir() if p.is_dir() else p.unlink()
    path.rmdir()


def find_copy(uid: str, which: str) -> Path:
    if which == "latest":
        found = copies(uid)
        if not found:
            raise KoboError(f"Локальних копій форми {uid} на цьому комп'ютері немає.")
        return found[0]
    path = Path(which).expanduser()
    if not path.is_absolute():
        path = next((p for p in copies(uid) if p.name == which), path)
    if not (path / "asset.json").is_file():
        raise KoboError(f"Копії {which} не знайдено. Подивіться список: kobo backups {uid}.")
    return path


# --- commands ----------------------------------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> int:
    token = sys.stdin.read().strip()
    if not re.fullmatch(r"[A-Za-z0-9]{20,100}", token):
        raise KoboError("Це не схоже на API-ключ Kobo: ключ — це рядок із 40 літер і цифр без пробілів. "
                        "Його видно на eu.kobotoolbox.org: Account Settings → Security → API Key → Display.")
    try:
        me = Kobo(server(), token).get("/me/")
    except KoboError as e:
        if e.status != 401:
            raise
        me = {}
    username = (me or {}).get("username")
    if not username or username == "AnonymousUser":
        raise KoboError("Ключ не підійшов до eu.kobotoolbox.org. Перевірте, що його взято саме з "
                        "eu.kobotoolbox.org (не з kf.kobotoolbox.org чи старого сервера), і скопіюйте ще раз.")
    if username in MAIN_ACCOUNTS:
        raise KoboError(f"Це ключ головного акаунта {username}. Ним користуватися не можна: потрібен ключ "
                        f"вашого особистого акаунта на eu.kobotoolbox.org. {ADMIN}.")
    save_token(token)
    state = load_state()
    state["username"] = username
    save_state(state)
    print(f"Готово: акаунт {username} на eu.kobotoolbox.org. Ключ збережено на цьому комп'ютері.")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    kobo = client()
    username = kobo.get("/me/").get("username")
    if username in MAIN_ACCOUNTS:
        raise KoboError(f"Цей ключ від головного акаунта {username}. З ним плагін не працює. {ADMIN}.")
    print(f"Акаунт: {username} на {urllib.parse.urlsplit(server()).hostname}")
    return 0


def cmd_forms(args: argparse.Namespace) -> int:
    kobo = client()
    me = account(kobo)
    forms = [describe(a, me) for a in list_forms(kobo)]
    if args.json:
        print(json.dumps(forms, ensure_ascii=False, indent=1))
        return 0
    if not forms:
        print("У цьому акаунті ще немає жодної форми.")
    for f in forms:
        orgs = "; ".join(f"{ORGS[o][0]}: {SHARING_UA[s]}" for o, s in f["sharing"].items())
        owner = "" if f["mine"] else f", власник: {f['owner']}"
        print(f"• «{f['name']}» — {f['uid']} — {STATUS_UA.get(f['status'], f['status'])}, "
              f"відповідей: {f['submissions']}{owner} — {orgs}")
    return 0


def cmd_check_sharing(args: argparse.Namespace) -> int:
    if args.daily:
        return daily_check()
    me, problems = sharing_problems(client())
    if args.json:
        print(json.dumps({"account": me, "problems": problems}, ensure_ascii=False, indent=1))
    elif problems:
        print(problem_text(problems))
    else:
        print("Усі ваші форми поділені з організацією з повними правами.")
    return 1 if problems else 0


def cmd_share(args: argparse.Namespace) -> int:
    kobo = client()
    account(kobo)
    names = share_with_orgs(kobo, args.uid, args.org)
    print(f"Готово: форма {args.uid} поділена з {names} з повними правами. Вона потрапить у нічний архів, "
          "а після розгортання (Deploy) — і в Google Таблицю організації.")
    return 0


def cmd_share_user(args: argparse.Namespace) -> int:
    if args.username in MAIN_ACCOUNTS:
        raise KoboError("Головні акаунти організацій додаються командою share --org.")
    kobo = client()
    account(kobo)
    try:
        kobo.get(f"/api/v2/users/{args.username}/")
    except KoboError as e:
        if e.status == 404:
            raise KoboError(f"Користувача {args.username} на eu.kobotoolbox.org немає. Потрібен логін "
                            "(username) колеги, не email.") from None
        raise
    grant(kobo, args.uid, args.username, ROLES[args.role])
    print(f"Готово: {args.username} має доступ до форми {args.uid} ({args.role}).")
    return 0


def cmd_unshare_user(args: argparse.Namespace) -> int:
    if args.username in MAIN_ACCOUNTS:
        raise KoboError(f"Доступ головного акаунта {args.username} відкликати не можна: без нього форма зникне "
                        "з архіву й Google Таблиць організації.")
    kobo = client()
    if args.username == account(kobo):
        raise KoboError("Власний доступ відкликати не можна.")
    path = f"/api/v2/assets/{args.uid}/"
    for p in kobo.get(path).get("permissions") or []:
        if _last(p["user"]) == args.username:
            kobo.delete(p["url"], ok=(204, 404))  # removing one may already have removed implied ones
    if grants(kobo.get(path)).get(args.username):
        raise KoboError(f"Kobo не відкликав усі права {args.username}. Спробуйте ще раз.")
    print(f"Готово: {args.username} більше не має доступу до форми {args.uid}.")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    kobo = client()
    account(kobo)
    path = make_backup(kobo, args.uid, args.reason)
    print(f"Копію зроблено: {path}")
    return 0


def cmd_backups(args: argparse.Namespace) -> int:
    found = copies(args.uid)
    if not found:
        print(f"Локальних копій форми {args.uid} немає.")
    for p in found:
        print(f"• {p.name} — {p}")
    return 0


def cmd_restore_form(args: argparse.Namespace) -> int:
    kobo = client()
    account(kobo)
    source = find_copy(args.uid, args.backup)
    saved = json.loads((source / "asset.json").read_text(encoding="utf-8"))
    if saved.get("uid") != args.uid:
        raise KoboError(f"Копія {source.name} належить іншій формі ({saved.get('uid')}), не {args.uid}.")
    versions = {v["uid"]: v for v in json.loads((source / "versions.json").read_text(encoding="utf-8"))}
    live = versions.get(saved.get("deployed_version_id") or "")
    content = live["content"] if live else saved.get("content")
    if not content:
        raise KoboError(f"У копії {source.name} немає опису форми.")
    fresh = make_backup(kobo, args.uid, f"перед поверненням до копії {source.name}")
    kobo.patch(f"/api/v2/assets/{args.uid}/", {"content": content})
    asset = kobo.get(f"/api/v2/assets/{args.uid}/")
    if asset.get("has_deployment"):
        deploy(kobo, args.uid, active=bool(asset.get("deployment__active", True)))
    print(f"Готово: форму {args.uid} повернуто до копії {source.name}"
          + (" і розгорнуто." if asset.get("has_deployment") else ".")
          + f" Стан перед поверненням збережено в {fresh}.")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kobo", description="Робота з KoboToolbox (eu.kobotoolbox.org) за правилами організації.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="зберегти API-ключ (ключ подається на stdin)").set_defaults(func=cmd_setup)
    sub.add_parser("whoami", help="який акаунт підключено").set_defaults(func=cmd_whoami)
    s = sub.add_parser("forms", help="усі форми: свої й поділені, стан поширення")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_forms)
    s = sub.add_parser("check-sharing", help="свої форми, не поділені з організацією")
    s.add_argument("--daily", action="store_true", help="для щоденної перевірки на початку сесії")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_check_sharing)
    s = sub.add_parser("share", help="поділитися формою з головним акаунтом організації (повні права)")
    s.add_argument("uid")
    s.add_argument("--org", required=True, choices=[*ORGS, "both"])
    s.set_defaults(func=cmd_share)
    s = sub.add_parser("share-user", help="дати доступ колезі")
    s.add_argument("uid")
    s.add_argument("username")
    s.add_argument("--role", required=True, choices=list(ROLES))
    s.set_defaults(func=cmd_share_user)
    s = sub.add_parser("unshare-user", help="відкликати доступ колеги")
    s.add_argument("uid")
    s.add_argument("username")
    s.set_defaults(func=cmd_unshare_user)
    s = sub.add_parser("backup", help="локальна копія форми й усіх відповідей (без фото)")
    s.add_argument("uid")
    s.add_argument("--reason", default="копія на прохання працівника")
    s.set_defaults(func=cmd_backup)
    s = sub.add_parser("backups", help="список локальних копій форми")
    s.add_argument("uid")
    s.set_defaults(func=cmd_backups)
    s = sub.add_parser("restore-form", help="повернути форму до локальної копії (спершу нова копія)")
    s.add_argument("uid")
    s.add_argument("--backup", required=True, help="latest, назва копії (дата-час) або шлях до неї")
    s.set_defaults(func=cmd_restore_form)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except KoboError as e:
        print(str(e), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
