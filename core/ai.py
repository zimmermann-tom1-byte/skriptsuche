"""Claude (Bildverständnis) und Voyage (Embeddings)."""
from __future__ import annotations

import base64
import io
import json
import re
import time

import httpx
from PIL import Image

try:  # iPad-Fotos kommen manchmal als HEIC
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:
    pass

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


# ---------- Hilfen ----------
def to_jpeg(data: bytes, max_side: int = 1568, quality: int = 80) -> bytes:
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _image_block(jpeg: bytes) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()},
    }


def _parse_json(text: str):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.JSONDecoder().raw_decode(text[start:])[0]  # ignoriert Text nach dem JSON


class AI:
    def __init__(self, anthropic_key: str | None, voyage_key: str | None,
                 index_model: str, query_model: str, voyage_model: str):
        self.claude = None
        if anthropic_key:
            import anthropic

            self.claude = anthropic.Anthropic(api_key=anthropic_key)
        self.voyage_key = voyage_key
        self.index_model = index_model
        self.query_model = query_model
        self.voyage_model = voyage_model

    # ---------- Indexierung ----------
    def describe_page(self, jpeg: bytes, page_text: str) -> str:
        """Beschreibt Formeln, Abbildungen und Handschrift einer Folie als Suchtext."""
        if not self.claude:
            return ""
        prompt = (
            "Das ist eine Seite aus Vorlesungsfolien (Ingenieurstudium, Mathe/Physik). "
            "Der maschinenlesbare Text der Seite steht unten. Ergänze NUR, was dort fehlt: "
            "Formeln aus Bildern (in einfacher Schreibweise, z. B. F = m*a, f'(x) = ...), "
            "was Abbildungen/Diagramme/Skizzen zeigen, und handschriftliche Notizen. "
            "Nenne am Ende 3–8 Fachbegriffe, unter denen man diese Seite suchen würde. "
            "Antworte knapp auf Deutsch, ohne Einleitung. Wenn nichts zu ergänzen ist, antworte nur mit '-'.\n\n"
            f"Text der Seite:\n{page_text[:3000]}"
        )
        msg = self.claude.messages.create(
            model=self.index_model,
            max_tokens=500,
            messages=[{"role": "user", "content": [_image_block(jpeg), {"type": "text", "text": prompt}]}],
        )
        out = "".join(b.text for b in msg.content if b.type == "text").strip()
        return "" if out == "-" else out

    def extract_topics(self, fach: str, name: str, pages: list[dict]) -> dict | None:
        """Themenübersicht eines Dokuments: Zusammenfassung + Themen mit Seitenbereichen."""
        if not self.claude or not pages:
            return None
        budget = max(300, 24000 // len(pages))  # ~24k Zeichen Gesamttext
        body = "\n\n".join(
            f"--- Seite {p['page_number']} ---\n{(p.get('content') or '')[:budget]}\n"
            f"{(p.get('figure_description') or '')[: budget // 3]}"
            for p in pages
        )
        prompt = (
            f"Fach: {fach}\nDatei: {name}\n\n"
            "Das ist der Inhalt eines Vorlesungsdokuments (Folien, Aufgabenblatt oder Handout) aus einem "
            "Ingenieurstudium. Erstelle eine Themenübersicht, damit ein Student sieht, was behandelt wurde.\n"
            "Antworte nur mit JSON:\n"
            '{"art": "Folien" | "Aufgaben" | "Handout" | "Sonstiges", '
            '"zusammenfassung": "1–2 Sätze", '
            '"themen": [{"titel": "Thema, wie es im Lehrbuch heißen würde", "von": erste_seite, "bis": letzte_seite, '
            '"inhalte": ["2–4 kurze Stichpunkte: zentrale Formeln, Regeln, Begriffe"]}]}\n'
            "3–10 Themen in Reihenfolge des Dokuments. Titelfolien, Gliederungen und Organisatorisches weglassen.\n\n"
            f"{body}"
        )
        msg = self.claude.messages.create(
            model=self.index_model, max_tokens=2000, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        data = _parse_json(text)
        if not isinstance(data, dict) or not isinstance(data.get("themen"), list):
            return None
        return data

    # ---------- Suche ----------
    def analyze_task(self, image: bytes | None, note: str) -> dict:
        """Erkennt aus Foto + Anmerkung das Thema. Rückgabe: thema, suchbegriffe, suchtext."""
        if not self.claude:
            return {"thema": note, "suchbegriffe": note.split(), "suchtext": note}
        content: list[dict] = []
        if image:
            content.append(_image_block(to_jpeg(image)))
        content.append({
            "type": "text",
            "text": (
                "Ich bin Student (Fahrzeugentwicklung, Mathe/Physik) und suche in meinen Vorlesungsfolien "
                "die Stellen, die ich zum Lösen dieser Aufgabe brauche (Formeln, Definitionen, Herleitungen, "
                "Beispiele). Löse die Aufgabe NICHT.\n"
                f"Meine Anmerkung: {note or '(keine)'}\n\n"
                "Antworte nur mit JSON:\n"
                '{"thema": "kurze Themenbeschreibung", '
                '"suchbegriffe": ["5–10 deutsche Fachbegriffe/Formelnamen, wie sie in Folien stehen würden"], '
                '"suchtext": "2–3 Sätze, die beschreiben, welcher Folieninhalt gebraucht wird"}'
            ),
        })
        msg = self.claude.messages.create(
            model=self.query_model, max_tokens=500, messages=[{"role": "user", "content": content}]
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        try:
            data = _parse_json(text)
        except Exception:
            data = {"thema": note, "suchbegriffe": note.split(), "suchtext": text[:500]}
        data.setdefault("suchbegriffe", [])
        data.setdefault("suchtext", data.get("thema", ""))
        return data

    def rerank(self, thema: str, suchtext: str, candidates: list[dict], top: int = 5) -> list[dict]:
        """Lässt Claude die besten Fundstellen auswählen und kurz begründen."""
        if not self.claude or not candidates:
            return [dict(c, grund="") for c in candidates[:top]]
        listing = "\n\n".join(
            f"[{i}] {c['fach']} / {c['name']}, S. {c['page_number']}\n"
            f"{(c.get('content') or '')[:700]}\n{(c.get('figure_description') or '')[:300]}"
            for i, c in enumerate(candidates)
        )
        prompt = (
            f"Gesuchtes Thema: {thema}\n{suchtext}\n\n"
            f"Kandidaten aus den Vorlesungsfolien:\n{listing}\n\n"
            f"Wähle die bis zu {top} hilfreichsten Seiten (beste zuerst). Lass unpassende weg. "
            'Antworte nur mit JSON: [{"nr": 0, "grund": "ein kurzer Satz, was auf der Seite hilft"}]'
        )
        msg = self.claude.messages.create(
            model=self.query_model, max_tokens=600, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        try:
            picks = _parse_json(text)
            out = []
            for p in picks:
                i = int(p["nr"])
                if 0 <= i < len(candidates) and all(o["page_id"] != candidates[i]["page_id"] for o in out):
                    out.append(dict(candidates[i], grund=p.get("grund", "")))
            return out[:top] or [dict(c, grund="") for c in candidates[:top]]
        except Exception:
            return [dict(c, grund="") for c in candidates[:top]]

    # ---------- Embeddings ----------
    def embed(self, texts: list[str], input_type: str) -> list[list[float]] | None:
        if not self.voyage_key or not texts:
            return None
        out: list[list[float]] = []
        for i in range(0, len(texts), 16):
            for attempt in range(5):  # Voyage drosselt Konten ohne Zahlungsmethode stark (429)
                r = httpx.post(
                    VOYAGE_URL,
                    headers={"Authorization": f"Bearer {self.voyage_key}"},
                    json={"input": texts[i : i + 16], "model": self.voyage_model,
                          "input_type": input_type, "output_dimension": 1024},
                    timeout=120,
                )
                if r.status_code != 429:
                    break
                time.sleep(min(60, 15 * (attempt + 1)))
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            out += [d["embedding"] for d in data]
        return out
