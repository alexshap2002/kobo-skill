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
from pathlib import Path
from typing import Any, Iterator

SERVER = "https://eu.kobotoolbox.org"
ORGS = {"bud-vilnyi": ("Будь вільний", "kobo_ymbefree"), "ye-dobro": ("Є добро", "kobo_edobro")}
MAIN_ACCOUNTS = {user for _, user in ORGS.values()}
ADMIN = "Олександр Шаповалов (Telegram @olexandr_shapovalov)"
RETRY_DELAYS = (2, 5, 15)
RETRY_STATUS = {429, 500, 502, 503, 504}


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
