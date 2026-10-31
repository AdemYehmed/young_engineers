#!/usr/bin/env python3
"""Copie yengineers/static vers public/static (Vercel sert public/ depuis son CDN).

À relancer si vous modifiez les CSS/JS/images : python scripts/build_public.py
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / "public" / "static"
if out.exists():
    shutil.rmtree(out)
shutil.copytree(ROOT / "yengineers" / "static", out)
print("public/static mis à jour")
