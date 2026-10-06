"""Skriptsuche – Foto einer Aufgabe hochladen, passende Folien finden."""
from __future__ import annotations

import hashlib

import streamlit as st

from core import graph
from core.ai import AI
from core.config import load_config
from core.db import DB
from core.indexer import index_pdf
from core.search import neighbour_pages, search
from core.sync import run_sync

st.set_page_config(page_title="Skriptsuche", page_icon="🔎", layout="wide")


@st.cache_resource
def services():
    cfg = load_config()
    db = DB(cfg.supabase_url, cfg.supabase_key)
    ai = AI(cfg.anthropic_key, cfg.voyage_key, cfg.index_model, cfg.query_model, cfg.voyage_model)
    return cfg, db, ai


cfg, db, ai = services()

# ---------- Passwortschutz ----------
if cfg.app_password and not st.session_state.get("auth"):
    st.title("🔎 Skriptsuche")
    pw = st.text_input("Passwort", type="password")
    if pw:
        if pw == cfg.app_password:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Falsches Passwort")
    st.stop()


@st.cache_data(ttl=300)
def faecher() -> list[dict]:
    return db.rpc("list_faecher", {}) or []


# ---------- Seitenleiste ----------
with st.sidebar:
    st.header("🔎 Skriptsuche")
    fl = faecher()
    optionen = ["Alle Fächer"] + [f["fach"] for f in fl]
    fach_wahl = st.selectbox("Fach", optionen)
    fach = None if fach_wahl == "Alle Fächer" else fach_wahl
    st.caption(f"{sum(f['dokumente'] for f in fl)} Dateien · {sum(f['seiten'] for f in fl)} Seiten im Index")

    if cfg.ms_client_id and st.button("🔄 Jetzt aktualisieren", use_container_width=True):
        with st.status("Gleiche OneDrive ab …", expanded=True) as status:
            try:
                s = run_sync(cfg, db, ai, log=st.write)
                status.update(label=f"Fertig: {s['neu']} neu, {s['aktualisiert']} aktualisiert, "
                                    f"{s['gelöscht']} entfernt", state="complete")
                faecher.clear()
            except graph.OneDriveNotConnected as e:
                status.update(label=str(e), state="error")
            except Exception as e:
                status.update(label=f"Fehler: {e}", state="error")

tab_suche, tab_upload, tab_setup = st.tabs(["Suchen", "Unterlagen hinzufügen", "Einrichtung"])

# ---------- Suchen ----------
with tab_suche:
    col_in, col_opt = st.columns([3, 2])
    with col_in:
        foto = st.file_uploader("Foto oder Screenshot der Aufgabe",
                                type=["jpg", "jpeg", "png", "heic", "heif", "webp"])
        notiz = st.text_input("Anmerkung oder Stichworte (optional)",
                              placeholder="z. B. „Wie leite ich hier ab?“ oder „Kettenregel“")
    with col_opt:
        if foto:
            try:
                st.image(foto, caption="Deine Aufgabe", use_container_width=True)
            except Exception:
                st.caption(f"📎 {foto.name}")
        use_ai = st.toggle("KI-Unterstützung", value=True,
                           help="Aus: reine Stichwortsuche, kostenlos (nur mit Stichworten, ohne Foto).")

    if st.button("Suchen", type="primary", disabled=not (foto or notiz)):
        if foto and not use_ai:
            st.warning("Für Fotos wird die KI-Unterstützung benötigt – ich schalte sie für diese Suche ein.")
            use_ai = True
        with st.spinner("Suche in deinen Unterlagen …"):
            try:
                st.session_state.result = search(db, ai, foto.getvalue() if foto else None,
                                                 notiz, fach, use_ai=use_ai)
            except Exception as e:
                st.error(f"Suche fehlgeschlagen: {e}")

    res = st.session_state.get("result")
    if res:
        info = res["info"]
        if info.get("thema"):
            st.markdown(f"**Erkanntes Thema:** {info['thema']}")
            if info.get("suchbegriffe"):
                st.caption("Gesucht nach: " + ", ".join(info["suchbegriffe"]))
        if not res["results"]:
            st.info("Nichts gefunden. Probier es mit anderen Stichworten oder einem anderen Fach.")
        for r in res["results"]:
            with st.container(border=True):
                st.markdown(f"### 📘 {r['fach']} → {r['name']}, S. {r['page_number']}")
                if r.get("grund"):
                    st.markdown(f"_{r['grund']}_")
                if r.get("image_url"):
                    st.image(r["image_url"], use_container_width=True)
                c1, c2 = st.columns(2)
                if r.get("web_url"):
                    c1.link_button("In OneDrive öffnen", r["web_url"])
                with c2.expander("Seite davor / danach"):
                    for nb in neighbour_pages(db, r["document_id"], r["page_number"]):
                        if nb.get("image_url"):
                            st.image(nb["image_url"], caption=f"S. {nb['page_number']}",
                                     use_container_width=True)

# ---------- Manuell hinzufügen ----------
with tab_upload:
    st.markdown("PDFs auswählen (auf dem iPad geht das direkt aus OneDrive), Fach wählen, „Einlesen“ tippen. "
                "Gleiche Datei nochmal hochladen = wird nicht doppelt aufgenommen.")
    files = st.file_uploader("PDFs", type=["pdf"], accept_multiple_files=True)
    vorhandene = [f["fach"] for f in faecher()]
    fach_neu = st.selectbox("Fach", vorhandene + ["(neues Fach)"]) if vorhandene else "(neues Fach)"
    if fach_neu == "(neues Fach)":
        fach_neu = st.text_input("Name des Fachs", placeholder="z. B. Mathematik 1")
    if st.button("Einlesen", disabled=not (files and fach_neu)):
        for f in files:
            data = f.getvalue()
            with st.spinner(f"Lese {f.name} ein …"):
                try:
                    n = index_pdf(db, ai, data, {
                        "onedrive_item_id": "upload:" + hashlib.sha256(data).hexdigest()[:32],
                        "name": f.name, "path": f"{fach_neu}/{f.name}", "fach": fach_neu,
                        "source": "upload",
                    }, log=st.write)
                    st.success(f"{f.name}: {n} Seiten aufgenommen")
                except Exception as e:
                    st.error(f"{f.name}: {e}")
        faecher.clear()

# ---------- Einrichtung ----------
with tab_setup:
    st.subheader("OneDrive")
    if not cfg.ms_client_id:
        st.info("OneDrive-Abgleich ist nicht eingerichtet. Neue PDFs bitte im Tab „Unterlagen hinzufügen“ "
                "aufnehmen. (Nachrüsten: MS_CLIENT_ID in den Secrets setzen.)")
    else:
        verbunden = bool(db.get_setting(graph.TOKEN_KEY))
        st.write("Status: " + ("✅ verbunden" if verbunden else "❌ nicht verbunden"))
        st.caption(f"Beobachteter Ordner: OneDrive/{cfg.onedrive_root}")
        if st.button("Mit OneDrive verbinden" if not verbunden else "Neu verbinden"):
            try:
                st.session_state.device = graph.start_device_login(cfg.ms_client_id)
            except Exception as e:
                st.error(f"Konnte Anmeldung nicht starten: {e}")
        dev = st.session_state.get("device")
        if dev:
            st.info(f"1. Öffne **{dev['verification_uri']}**\n\n"
                    f"2. Gib diesen Code ein: **{dev['user_code']}**\n\n"
                    "3. Melde dich mit deinem privaten Microsoft-Konto an und bestätige.\n\n"
                    "4. Komm zurück und tippe auf „Anmeldung abschließen“.")
            st.link_button("Anmeldeseite öffnen", dev["verification_uri"])
            if st.button("Anmeldung abschließen"):
                r = graph.finish_device_login(cfg.ms_client_id, dev["device_code"], db)
                if r == "ok":
                    st.success("OneDrive verbunden! Tippe links auf „Jetzt aktualisieren“ für den ersten Abgleich.")
                    del st.session_state.device
                elif r == "pending":
                    st.warning("Noch nicht bestätigt – erst die Anmeldung abschließen, dann erneut tippen.")
                else:
                    st.error(f"Fehler: {r}")
                    del st.session_state.device

    st.subheader("Dienste")
    st.write("Claude (Bilderkennung): " + ("✅" if cfg.anthropic_key else "❌ ANTHROPIC_API_KEY fehlt"))
    st.write("Voyage (Bedeutungssuche): " + ("✅" if cfg.voyage_key else "➖ optional, nicht gesetzt"))
