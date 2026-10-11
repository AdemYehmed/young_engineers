#!/usr/bin/env python3
"""Initialise la base SQLite. Idempotent : n'efface et n'écrase jamais de données existantes."""
from dotenv import load_dotenv

load_dotenv()

from config import build_config  # noqa: E402
from yengineers.db import init_db  # noqa: E402


def main():
    cfg = build_config()
    existed = __import__("pathlib").Path(cfg["DATABASE"]).exists()
    init_db(cfg["DATABASE"])
    print(("Base existante conservée et vérifiée : " if existed else "Base créée : ") + cfg["DATABASE"])


if __name__ == "__main__":
    main()
