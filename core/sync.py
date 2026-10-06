"""Gleicht den OneDrive-Ordner mit dem Suchindex ab (neu / geändert / gelöscht)."""
from __future__ import annotations

from typing import Callable

from . import graph
from .ai import AI
from .config import Config
from .db import DB
from .indexer import delete_document, index_pdf


def run_sync(cfg: Config, db: DB, ai: AI, log: Callable[[str], None] = print) -> dict:
    if not cfg.ms_client_id:
        raise RuntimeError("MS_CLIENT_ID fehlt.")
    token = graph.get_access_token(cfg.ms_client_id, db)
    remote = graph.list_pdfs(token, cfg.onedrive_root)
    log(f"📂 {len(remote)} PDFs in OneDrive/{cfg.onedrive_root}")

    known = {
        d["onedrive_item_id"]: d
        for d in db.select("documents", {"source": "eq.onedrive",
                                         "select": "id,onedrive_item_id,content_tag,indexed_at,path"})
    }
    remote_ids = {f["id"] for f in remote}

    stats = {"neu": 0, "aktualisiert": 0, "gelöscht": 0, "seiten": 0, "fehler": 0}

    for item_id, d in known.items():
        if item_id not in remote_ids:
            log(f"🗑  entfernt: {d['path']}")
            delete_document(db, d["id"])
            stats["gelöscht"] += 1

    todo = [f for f in remote
            if f["id"] not in known
            or known[f["id"]]["content_tag"] != f["tag"]
            or not known[f["id"]]["indexed_at"]]
    log(f"🔄 {len(todo)} Dateien einzulesen")

    for f in todo:
        is_new = f["id"] not in known
        log(f"→ {f['path']}")
        try:
            pdf = graph.download(token, f["id"])
            n = index_pdf(db, ai, pdf, {
                "onedrive_item_id": f["id"], "name": f["name"], "path": f["path"], "fach": f["fach"],
                "content_tag": f["tag"], "last_modified": f["modified"], "web_url": f["web_url"],
                "source": "onedrive",
            }, log=log)
            stats["seiten"] += n
            stats["neu" if is_new else "aktualisiert"] += 1
            log(f"   ✓ {n} Seiten")
        except Exception as e:
            stats["fehler"] += 1
            log(f"   ✗ Fehler: {e}")
    return stats
