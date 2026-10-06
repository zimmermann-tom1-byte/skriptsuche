"""Zentrale Konfiguration.

Werte kommen aus Streamlit-Secrets (App) oder Umgebungsvariablen (GitHub Actions).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


_SECRETS_ERROR: str | None = None


def _get(name: str, default: str | None = None) -> str | None:
    global _SECRETS_ERROR
    val = os.environ.get(name)
    if val:
        return val
    try:  # Streamlit ist im Sync-Job evtl. nicht geladen
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except ModuleNotFoundError:
        pass
    except Exception as e:  # z. B. Tippfehler im Secrets-Text (TOML)
        _SECRETS_ERROR = f"{type(e).__name__}: {e}"
    return default


def _secret_names() -> list[str]:
    try:
        import streamlit as st

        return list(st.secrets.keys())
    except Exception:
        return []


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_key: str
    anthropic_key: str | None
    voyage_key: str | None
    ms_client_id: str | None
    onedrive_root: str
    index_model: str
    query_model: str
    voyage_model: str
    app_password: str | None


def load_config() -> Config:
    url = _get("SUPABASE_URL")
    key = _get("SUPABASE_SECRET_KEY")
    if not url or not key:
        if _SECRETS_ERROR:
            hint = f"Die Secrets konnten nicht gelesen werden – vermutlich ein Tippfehler ({_SECRETS_ERROR[:200]})."
        else:
            found = ", ".join(_secret_names()) or "keine"
            hint = f"Gefundene Secrets: {found}."
        raise RuntimeError(f"SUPABASE_URL und SUPABASE_SECRET_KEY müssen gesetzt sein. {hint}")
    return Config(
        supabase_url=url.rstrip("/"),
        supabase_key=key,
        anthropic_key=_get("ANTHROPIC_API_KEY"),
        voyage_key=_get("VOYAGE_API_KEY"),
        ms_client_id=_get("MS_CLIENT_ID"),
        onedrive_root=(_get("ONEDRIVE_ROOT", "Studium") or "Studium").strip("/"),
        index_model=_get("INDEX_MODEL", "claude-haiku-4-5") or "claude-haiku-4-5",
        query_model=_get("QUERY_MODEL", "claude-haiku-4-5") or "claude-haiku-4-5",
        voyage_model=_get("VOYAGE_MODEL", "voyage-4") or "voyage-4",
        app_password=_get("APP_PASSWORD"),
    )
