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
            raise KoboError("Сервер Kobo зараз не відповідає. Спробуйте за кілька хвилин.")
        if status == 401:
            raise KoboError("Kobo не прийняв ключ. Можливо, його змінили: попросіть працівника дати новий "
                            "API-ключ і збережіть його командою setup.")
        if status == 403:
            raise KoboError("Kobo каже, що у вашого акаунта немає на це прав.")
        if status == 404:
            raise KoboError("Kobo не знайшов цю форму чи запис. Можливо, його вже видалили або код неправильний.")
        raise KoboError(f"Kobo відхилив запит ({status}): {_kobo_says(payload)}")

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


# --- commands ----------------------------------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> int:
    token = sys.stdin.read().strip()
    if not re.fullmatch(r"[A-Za-z0-9]{20,100}", token):
        raise KoboError("Це не схоже на API-ключ Kobo: ключ — це рядок із 40 літер і цифр без пробілів. "
                        "Його видно на eu.kobotoolbox.org: Account Settings → Security → API Key → Display.")
    try:
        me = Kobo(server(), token).get("/me/")
    except KoboError as e:
        if "не прийняв ключ" not in str(e):
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


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kobo", description="Робота з KoboToolbox (eu.kobotoolbox.org) за правилами організації.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="зберегти API-ключ (ключ подається на stdin)").set_defaults(func=cmd_setup)
    sub.add_parser("whoami", help="який акаунт підключено").set_defaults(func=cmd_whoami)
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
