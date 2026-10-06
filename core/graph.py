"""Zugriff auf das private OneDrive über Microsoft Graph.

Anmeldung per Device-Code-Flow (öffentlicher Client, kein Secret nötig).
Der Refresh-Token liegt in Supabase (Tabelle app_settings) und wird bei
jeder Nutzung erneuert.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

from .db import DB

AUTHORITY = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = "Files.Read offline_access"
TOKEN_KEY = "ms_refresh_token"


class OneDriveNotConnected(RuntimeError):
    pass


# ---------- Anmeldung ----------
def start_device_login(client_id: str) -> dict:
    """Liefert user_code, verification_uri, device_code, message."""
    r = httpx.post(f"{AUTHORITY}/devicecode", data={"client_id": client_id, "scope": SCOPES}, timeout=30)
    r.raise_for_status()
    return r.json()


def finish_device_login(client_id: str, device_code: str, db: DB) -> str:
    """Gibt 'ok', 'pending' oder eine Fehlermeldung zurück."""
    r = httpx.post(
        f"{AUTHORITY}/token",
        data={
            "client_id": client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        },
        timeout=30,
    )
    data = r.json()
    if "refresh_token" in data:
        db.set_setting(TOKEN_KEY, data["refresh_token"])
        return "ok"
    err = data.get("error", "")
    if err in ("authorization_pending", "slow_down"):
        return "pending"
    return data.get("error_description", err or "Unbekannter Fehler")


def get_access_token(client_id: str, db: DB) -> str:
    refresh = db.get_setting(TOKEN_KEY)
    if not refresh:
        raise OneDriveNotConnected("OneDrive ist noch nicht verbunden (Tab „Einrichtung“).")
    r = httpx.post(
        f"{AUTHORITY}/token",
        data={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "scope": SCOPES,
        },
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise OneDriveNotConnected(
            "OneDrive-Anmeldung abgelaufen – bitte im Tab „Einrichtung“ neu verbinden. "
            f"({data.get('error_description', data.get('error', ''))[:150]})"
        )
    if data.get("refresh_token"):
        db.set_setting(TOKEN_KEY, data["refresh_token"])
    return data["access_token"]


# ---------- Dateien ----------
def _get_all(client: httpx.Client, url: str) -> list[dict]:
    items: list[dict] = []
    while url:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
        items += data.get("value", [])
        url = data.get("@odata.nextLink")
    return items


def list_pdfs(token: str, root: str) -> list[dict]:
    """Alle PDFs unterhalb von /<root>, rekursiv.

    Rückgabe je Datei: id, name, path (relativ zu root), fach, tag, modified, web_url
    """
    sel = "$select=id,name,folder,file,cTag,eTag,lastModifiedDateTime,webUrl&$top=200"
    client = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60)
    start = f"{GRAPH}/me/drive/root:/{quote(root)}:/children?{sel}"
    out: list[dict] = []
    stack: list[tuple[str, str]] = [(start, "")]
    while stack:
        url, rel = stack.pop()
        for it in _get_all(client, url):
            name = it["name"]
            if "folder" in it:
                stack.append((f"{GRAPH}/me/drive/items/{it['id']}/children?{sel}", f"{rel}{name}/"))
            elif name.lower().endswith(".pdf"):
                out.append(
                    {
                        "id": it["id"],
                        "name": name,
                        "path": f"{rel}{name}",
                        "fach": rel.rstrip("/") or "Allgemein",
                        "tag": it.get("cTag") or it.get("eTag"),
                        "modified": it.get("lastModifiedDateTime"),
                        "web_url": it.get("webUrl"),
                    }
                )
    return out


def download(token: str, item_id: str) -> bytes:
    r = httpx.get(
        f"{GRAPH}/me/drive/items/{item_id}/content",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=True,
        timeout=180,
    )
    r.raise_for_status()
    return r.content
