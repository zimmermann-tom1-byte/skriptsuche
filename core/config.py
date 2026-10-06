"""Zentrale Konfiguration.

Werte kommen aus Streamlit-Secrets (App) oder Umgebungsvariablen (GitHub Actions).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    try:  # Streamlit ist im Sync-Job evtl. nicht geladen
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


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
        raise RuntimeError("SUPABASE_URL und SUPABASE_SECRET_KEY müssen gesetzt sein.")
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
