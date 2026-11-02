"""Igienă repo: fără binare rătăcite în rădăcina ramurii principale."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTERZIS = (".whl", ".zip", ".sqlite", ".db", ".tar.gz")


def test_fara_binare_in_radacina():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    gasite = [f for f in out if "/" not in f and f.endswith(INTERZIS)]
    assert not gasite, f"Fișiere binare urmărite în rădăcină: {gasite}"
