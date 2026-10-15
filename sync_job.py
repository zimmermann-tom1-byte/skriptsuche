"""Nächtlicher Abgleich (GitHub Actions): python sync_job.py"""
import os
import sys

from core.ai import AI
from core.config import load_config
from core.db import DB
from core.sync import run_sync


def main() -> int:
    names = ["SUPABASE_URL", "SUPABASE_SECRET_KEY", "ANTHROPIC_API_KEY", "VOYAGE_API_KEY",
             "MS_CLIENT_ID", "ONEDRIVE_ROOT"]
    for n in names:  # nur ob gesetzt – Werte werden nie ausgegeben
        print(f"{n}: {'gesetzt' if os.environ.get(n) else 'FEHLT'}")
    missing = [n for n in names[:2] + ["MS_CLIENT_ID"] if not os.environ.get(n)]
    if missing:
        print(f"::error::GitHub-Secrets fehlen oder sind leer: {', '.join(missing)} "
              "(Settings → Secrets and variables → Actions → Reiter 'Secrets')")
        return 1
    cfg = load_config()
    db = DB(cfg.supabase_url, cfg.supabase_key)
    ai = AI(cfg.anthropic_key, cfg.voyage_key, cfg.index_model, cfg.query_model, cfg.voyage_model)
    stats = run_sync(cfg, db, ai)
    print("Ergebnis:", stats)
    return 1 if stats["fehler"] else 0


if __name__ == "__main__":
    sys.exit(main())
