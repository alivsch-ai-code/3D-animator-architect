"""Lädt docs/STANDARDS.md als Kontext für das Grundriss-Parsing-Prompt.

Siehe docs/STANDARDS.md Abschnitt 5 für die Priorisierung der geladenen Normen.
"""
from functools import lru_cache

from app.core.config import get_settings

# Praxis-Spickzettel (docs/STANDARDS.md Abschnitt 3) wird zusätzlich als kompakte
# Tabelle mitgegeben, da das LLM diese Schwellenwerte direkt auf jede Wand/Öffnung
# anwenden muss, nicht nur als Hintergrundwissen lesen soll.
PRACTICAL_CHEATSHEET = """\
Praxis-Schwellenwerte (DACH-Wohnbau, als Plausibilitätsprüfung anzuwenden):
- Maßstäbe: 1:50 (Wohnung, Möbeldetail), 1:100 (Gesamtgebäude), 1:20 (Details)
- Wandstärken: Innenwand nicht tragend 10-15cm, Innenwand tragend 15-30cm, \
Außenwand 20-37,5cm
- Türbreiten: Standard-Innentür 80-90cm, barrierefrei (DIN 18040-2) >= 90cm \
lichte Breite
- Deckenhöhe Wohnraum: üblich 2,4-2,6m
- Fensterbrüstung: üblich 0 (bodentief), 0,6m (Standard), 0,9m (Küche/Bad)
"""


@lru_cache
def load_standards_context() -> str:
    settings = get_settings()
    try:
        standards_md = settings.standards_doc_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        standards_md = "(docs/STANDARDS.md nicht gefunden - nur Praxis-Spickzettel verfuegbar)"

    return (
        "# Referenz: Bau- und Zeichnungsstandards\n\n"
        f"{standards_md}\n\n"
        "# Praxis-Spickzettel\n\n"
        f"{PRACTICAL_CHEATSHEET}"
    )
