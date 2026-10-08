"""Themenübersicht: was wurde bisher behandelt? Plus Index-Wartung."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Callable

from .ai import AI
from .db import DB

_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?(?!\d)")


def date_from_name(name: str, today: date | None = None) -> date | None:
    """'Mengenlehre 30.9..pdf' → 2026-09-30. Ohne Jahr: das Jahr, das nicht in der Zukunft liegt."""
    today = today or date.today()
    for m in _DATE_RE.finditer(name):
        d, mth, y = int(m.group(1)), int(m.group(2)), m.group(3)
        try:
            if y:
                year = int(y) + (2000 if len(y) == 2 else 0)
                return date(year, mth, d)
            cand = date(today.year, mth, d)
            if (cand - today).days > 31:
                cand = date(today.year - 1, mth, d)
            return cand
        except ValueError:
            continue
    return None


def build_topics(db: DB, ai: AI, document_id: str, fach: str, name: str) -> dict | None:
    pages = db.select("pages", {
        "document_id": f"eq.{document_id}",
        "select": "page_number,content,figure_description", "order": "page_number",
    })
    topics = ai.extract_topics(fach, name, pages)
    if topics is not None:
        db.update("documents", {"id": f"eq.{document_id}"}, {"topics": topics})
    return topics


def documents_overview(db: DB, fach: str | None = None) -> list[dict]:
    params = {
        "select": "id,fach,name,lecture_date,indexed_at,page_count,topics",
        "order": "fach,lecture_date.asc.nullslast,name",
    }
    if fach:
        params["fach"] = f"eq.{fach}"
    rows = db.select("documents", params)
    for r in rows:
        if isinstance(r.get("topics"), str):
            try:
                r["topics"] = json.loads(r["topics"])
            except Exception:
                r["topics"] = None
    return rows


def backfill(db: DB, ai: AI, log: Callable[[str], None] = print) -> dict:
    """Fehlende Daten nachholen: Vorlesungsdatum, Themen, Embeddings."""
    stats = {"themen": 0, "embeddings": 0, "fehler": 0}
    docs = db.select("documents", {"select": "id,fach,name,lecture_date,topics,indexed_at"})

    for d in docs:
        if not d.get("indexed_at"):
            continue
        if not d.get("lecture_date"):
            ld = date_from_name(d["name"])
            if ld:
                db.update("documents", {"id": f"eq.{d['id']}"}, {"lecture_date": ld.isoformat()})
        if not d.get("topics"):
            log(f"📝 Themen: {d['fach']} / {d['name']}")
            try:
                if build_topics(db, ai, d["id"], d["fach"], d["name"]):
                    stats["themen"] += 1
            except Exception as e:
                stats["fehler"] += 1
                log(f"   ✗ {e}")

    if ai.voyage_key:
        missing = db.select("pages", {
            "embedding": "is.null",
            "select": "id,page_number,content,figure_description,documents(fach,name)",
            "limit": "500",
        })
        if missing:
            log(f"🧭 {len(missing)} Seiten ohne Bedeutungs-Index – hole nach …")
        for k in range(0, len(missing), 16):
            chunk = missing[k : k + 16]
            texts = [
                f"{(p.get('documents') or {}).get('fach', '')} | {(p.get('documents') or {}).get('name', '')} | "
                f"Seite {p['page_number']}\n{p['content']}\n{p['figure_description']}"[:8000]
                for p in chunk
            ]
            try:
                vecs = ai.embed(texts, "document") or []
                for p, v in zip(chunk, vecs):
                    db.update("pages", {"id": f"eq.{p['id']}"},
                              {"embedding": "[" + ",".join(f"{x:.6f}" for x in v) + "]"})
                    stats["embeddings"] += 1
            except Exception as e:
                stats["fehler"] += 1
                log(f"   ✗ Embeddings: {e}")
                break
    return stats
