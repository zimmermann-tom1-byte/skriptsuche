"""Nächtlicher Abgleich (GitHub Actions): python sync_job.py"""
import sys

from core.ai import AI
from core.config import load_config
from core.db import DB
from core.sync import run_sync


def main() -> int:
    cfg = load_config()
    db = DB(cfg.supabase_url, cfg.supabase_key)
    ai = AI(cfg.anthropic_key, cfg.voyage_key, cfg.index_model, cfg.query_model, cfg.voyage_model)
    stats = run_sync(cfg, db, ai)
    print("Ergebnis:", stats)
    return 1 if stats["fehler"] else 0


if __name__ == "__main__":
    sys.exit(main())
