"""Schlanker Supabase-Client (PostgREST + Storage) auf Basis von httpx."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

BUCKET = "pages"


def _clean(value):
    """Postgres-Text darf keine Null-Zeichen enthalten (kommen in manchen PDFs vor)."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


class DB:
    def __init__(self, url: str, key: str):
        self.url = url
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        self.http = httpx.Client(headers=headers, timeout=60)

    # ---------- PostgREST ----------
    def _rest(self, method: str, path: str, **kw) -> Any:
        r = self.http.request(method, f"{self.url}/rest/v1/{path}", **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {method} {path}: {r.status_code} {r.text[:300]}")
        if r.content and "json" in r.headers.get("content-type", ""):
            return r.json()
        return None

    def select(self, table: str, params: dict[str, str]) -> list[dict]:
        return self._rest("GET", table, params=params)

    def insert(self, table: str, rows: list[dict] | dict, upsert_on: str | None = None) -> list[dict]:
        headers = {"Prefer": "return=representation"}
        params = {}
        if upsert_on:
            headers["Prefer"] += ",resolution=merge-duplicates"
            params["on_conflict"] = upsert_on
        return self._rest("POST", table, json=_clean(rows), headers=headers, params=params)

    def update(self, table: str, match: dict[str, str], values: dict) -> None:
        self._rest("PATCH", table, params=match, json=_clean(values))

    def delete(self, table: str, match: dict[str, str]) -> None:
        self._rest("DELETE", table, params=match)

    def rpc(self, fn: str, args: dict) -> Any:
        return self._rest("POST", f"rpc/{fn}", json=args)

    # ---------- Einstellungen (z. B. OneDrive-Refresh-Token) ----------
    def get_setting(self, key: str) -> str | None:
        rows = self.select("app_settings", {"key": f"eq.{key}", "select": "value"})
        return rows[0]["value"] if rows else None

    def set_setting(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.insert("app_settings", {"key": key, "value": value, "updated_at": now}, upsert_on="key")

    # ---------- Storage ----------
    def upload_image(self, path: str, data: bytes) -> None:
        r = self.http.post(
            f"{self.url}/storage/v1/object/{BUCKET}/{quote(path)}",
            content=data,
            headers={"Content-Type": "image/jpeg", "x-upsert": "true"},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Upload {path}: {r.status_code} {r.text[:200]}")

    def delete_images(self, paths: list[str]) -> None:
        for i in range(0, len(paths), 500):
            chunk = paths[i : i + 500]
            if chunk:
                self.http.request(
                    "DELETE", f"{self.url}/storage/v1/object/{BUCKET}", json={"prefixes": chunk}
                )

    def signed_urls(self, paths: list[str], expires: int = 3600) -> dict[str, str]:
        paths = [p for p in paths if p]
        if not paths:
            return {}
        r = self.http.post(
            f"{self.url}/storage/v1/object/sign/{BUCKET}",
            json={"expiresIn": expires, "paths": paths},
        )
        r.raise_for_status()
        out = {}
        for item in r.json():
            if item.get("signedURL"):
                out[item["path"]] = f"{self.url}/storage/v1{item['signedURL']}"
        return out
