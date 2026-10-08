"""Liest PDFs seitenweise ein: Text, Seitenbild, KI-Beschreibung, Embedding."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import fitz  # PyMuPDF

from .ai import AI
from .db import DB
from .topics import build_topics, date_from_name


def _needs_vision(page: "fitz.Page", text: str) -> bool:
    """Nur Seiten mit Bildern, Zeichnungen, Handschrift oder wenig Text an Claude schicken."""
    if len(text.strip()) < 250:
        return True
    if page.get_images(full=False):
        return True
    try:
        if any(a.type[0] == fitz.PDF_ANNOT_INK for a in page.annots() or []):
            return True
        if len(page.get_drawings()) > 25:
            return True
    except Exception:
        pass
    return False


def _lecture_date(meta: dict) -> str | None:
    d = meta.get("lecture_date") or date_from_name(meta["name"])
    return str(d) if d else None


def _clear_document_pages(db: DB, document_id: str) -> None:
    old = db.select("pages", {"document_id": f"eq.{document_id}", "select": "image_path"})
    db.delete_images([p["image_path"] for p in old if p.get("image_path")])
    db.delete("pages", {"document_id": f"eq.{document_id}"})


def index_pdf(
    db: DB,
    ai: AI,
    pdf_bytes: bytes,
    meta: dict,
    log: Callable[[str], None] = print,
    use_vision: bool = True,
) -> int:
    """meta: onedrive_item_id, name, path, fach, content_tag, last_modified, web_url, source"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    row = db.insert(
        "documents",
        {
            "onedrive_item_id": meta["onedrive_item_id"],
            "name": meta["name"],
            "path": meta["path"],
            "fach": meta["fach"],
            "content_tag": meta.get("content_tag"),
            "last_modified": meta.get("last_modified"),
            "web_url": meta.get("web_url"),
            "source": meta.get("source", "onedrive"),
            "page_count": doc.page_count,
            "lecture_date": _lecture_date(meta),
            "topics": None,
            "indexed_at": None,  # wird erst am Ende gesetzt → Abbruch = nächster Lauf versucht erneut
        },
        upsert_on="onedrive_item_id",
    )[0]
    document_id = row["id"]
    _clear_document_pages(db, document_id)

    pages: list[dict] = []
    for i, page in enumerate(doc):
        n = i + 1
        text = page.get_text("text").strip()
        # Seitenbild für die Anzeige (~110 dpi)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        jpeg = pix.tobytes("jpeg", jpg_quality=72)
        image_path = f"{document_id}/{n:04d}.jpg"
        db.upload_image(image_path, jpeg)

        desc = ""
        if use_vision and _needs_vision(page, text):
            try:
                desc = ai.describe_page(jpeg, text)
            except Exception as e:  # Indexierung nicht wegen einer Seite abbrechen
                log(f"    ⚠ KI-Beschreibung S. {n} fehlgeschlagen: {e}")
        pages.append({"document_id": document_id, "page_number": n, "content": text,
                      "figure_description": desc, "image_path": image_path})

    embed_inputs = [
        f"{meta['fach']} | {meta['name']} | Seite {p['page_number']}\n{p['content']}\n{p['figure_description']}"[:8000]
        for p in pages
    ]
    try:
        vectors = ai.embed(embed_inputs, "document")
    except Exception as e:
        log(f"    ⚠ Embeddings fehlgeschlagen ({e}) – nur Volltextsuche für diese Datei")
        vectors = None
    if vectors:
        for p, v in zip(pages, vectors):
            p["embedding"] = "[" + ",".join(f"{x:.6f}" for x in v) + "]"

    for k in range(0, len(pages), 50):
        db.insert("pages", pages[k : k + 50])

    db.update("documents", {"id": f"eq.{document_id}"},
              {"indexed_at": datetime.now(timezone.utc).isoformat()})
    try:
        build_topics(db, ai, document_id, meta["fach"], meta["name"])
    except Exception as e:  # Themen lassen sich später nachholen
        log(f"    ⚠ Themenübersicht fehlgeschlagen: {e}")
    return doc.page_count


def delete_document(db: DB, document_id: str) -> None:
    _clear_document_pages(db, document_id)
    db.delete("documents", {"id": f"eq.{document_id}"})
