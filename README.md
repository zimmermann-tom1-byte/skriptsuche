# 🔎 Skriptsuche

Foto einer Aufgabe hochladen → die passenden Stellen in den Vorlesungsfolien finden und direkt ansehen.

**So funktioniert es**
- Jede Nacht gleicht ein GitHub-Actions-Job den OneDrive-Ordner `Studium/` ab. Neue oder geänderte PDFs werden seitenweise eingelesen, gelöschte entfernt. Das Fach ergibt sich aus dem Ordnerpfad, zum Beispiel `Vorkurse/Mathematik`.
- Pro Seite werden gespeichert: der Text, ein Seitenbild und bei Abbildungen, Formeln in Bildern oder Handschrift eine kurze Beschreibung von Claude. Dazu kommt ein Embedding von Voyage für die Bedeutungssuche.
- Bei einer Suche erkennt Claude das Thema auf dem Foto. Supabase sucht dann gleichzeitig per deutschem Volltext und per Bedeutung, und Claude wählt die besten Seiten aus und begründet die Auswahl kurz.

## Aufbau

| Datei | Zweck |
|---|---|
| `app.py` | Streamlit-Oberfläche (Suchen, PDFs manuell hinzufügen, Einrichtung) |
| `sync_job.py` | nächtlicher Abgleich (GitHub Actions) |
| `core/graph.py` | OneDrive über Microsoft Graph (Device-Code-Anmeldung, Refresh-Token in Supabase) |
| `core/indexer.py` | PDF → Seiten, Bilder, Beschreibungen, Embeddings |
| `core/search.py` | Suche und Auswahl |
| `core/ai.py` | Claude und Voyage |
| `core/db.py` | Supabase (REST und Storage) |
| `supabase/migrations/` | Datenbankschema |

## Secrets

Diese Werte werden in Streamlit (*App → Settings → Secrets*) und in GitHub (*Settings → Secrets and variables → Actions*) eingetragen:

```toml
SUPABASE_URL = "https://pmjspjlklnhkgxfrmbzd.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_..."      # Supabase → Project Settings → API Keys → Secret key
ANTHROPIC_API_KEY = "sk-ant-..."
VOYAGE_API_KEY = "pa-..."                   # optional
MS_CLIENT_ID = "xxxxxxxx-xxxx-..."
APP_PASSWORD = "..."                        # nur Streamlit
```

Optional kannst du noch diese Werte setzen: `ONEDRIVE_ROOT` (Standard `Studium`), `INDEX_MODEL` und `QUERY_MODEL` (Standard `claude-haiku-4-5`) sowie `VOYAGE_MODEL` (Standard `voyage-4`).

## Kosten (grob)
- Suche mit Foto: etwa 1 Cent (Claude Haiku 4.5).
- Stichwortsuche ohne KI: kostenlos.
- Einlesen: Getippte Seiten ohne Abbildungen kosten nichts. Seiten mit Abbildungen kosten etwa 0,2–0,3 Cent pro Seite.
- Voyage: Die ersten 200 Mio. Tokens sind kostenlos.
- Supabase, Streamlit Community Cloud und GitHub Actions: im kostenlosen Rahmen.
