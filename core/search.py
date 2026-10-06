"""Suche: Foto/Text → Suchbegriffe → hybride Suche in Supabase → KI-Auswahl."""
from __future__ import annotations

from .ai import AI
from .db import DB


def _or_query(terms: list[str]) -> str:
    """websearch_to_tsquery-Syntax: Begriffe mit OR verknüpfen, Mehrwortbegriffe als Phrase."""
    parts = []
    for t in terms:
        t = t.replace('"', "").strip()
        if t:
            parts.append(f'"{t}"' if " " in t else t)
    return " or ".join(parts)


def search(db: DB, ai: AI, image: bytes | None, note: str, fach: str | None,
           use_ai: bool = True, top: int = 5) -> dict:
    if use_ai and (image or note):
        info = ai.analyze_task(image, note)
    else:
        info = {"thema": note, "suchbegriffe": note.split(), "suchtext": note}

    terms = list(dict.fromkeys([*info.get("suchbegriffe", []), *note.split()]))
    query_text = _or_query(terms)
    semantic = f"{info.get('thema', '')}. {info.get('suchtext', '')} {' '.join(terms)}".strip()

    vec = None
    try:
        e = ai.embed([semantic], "query")
        if e:
            vec = "[" + ",".join(f"{x:.6f}" for x in e[0]) + "]"
    except Exception:
        vec = None

    candidates = db.rpc("search_pages", {
        "query_text": query_text, "query_embedding": vec, "fach_filter": fach, "match_count": 12,
    }) or []

    if use_ai and ai.claude:
        results = ai.rerank(info.get("thema", ""), info.get("suchtext", ""), candidates, top=top)
    else:
        results = [dict(c, grund="") for c in candidates[:top]]

    urls = db.signed_urls([r["image_path"] for r in results])
    for r in results:
        r["image_url"] = urls.get(r["image_path"])
    return {"info": info, "results": results}


def neighbour_pages(db: DB, document_id: str, page_number: int) -> list[dict]:
    rows = db.select("pages", {
        "document_id": f"eq.{document_id}",
        "page_number": f"in.({page_number - 1},{page_number + 1})",
        "select": "page_number,image_path", "order": "page_number",
    })
    urls = db.signed_urls([r["image_path"] for r in rows])
    return [dict(r, image_url=urls.get(r["image_path"])) for r in rows]
