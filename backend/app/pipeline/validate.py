"""Plausibilitaets-/Konsistenzpruefung der geparsten Geometrie.

Live-Test (2026-10-11, siehe docs/ARCHITECTURE.md): Der Parser (auch starke
Modelle wie Claude Opus 4.6) liefert nicht immer eine geometrisch konsistente
Ausgabe - z.B. wurde in einem Lauf ein Balkon-Polygon FAELSCHLICH innerhalb
des Wohnzimmer-Polygons platziert statt ausserhalb der Fassade. Reale
Raeume duerfen sich nie ueberlappen. Diese Pruefung macht solche Fehler
SICHTBAR (als compliance_flag) statt sie als stillen, "huebsch aussehenden"
aber falschen 3D-Modell/Render-Fehler durchzureichen - konsistent mit der
Architekturentscheidung, Geometrie nie blind zu vertrauen.
"""
from __future__ import annotations

from shapely.geometry import Polygon

from app.models.schemas import ComplianceFlag, FloorPlanGeometry

# Ab diesem Anteil der kleineren Raumflaeche gilt eine Ueberlappung als
# gravierender Fehler (nicht nur Rundungstoleranz an einer gemeinsamen Wand).
_OVERLAP_RATIO_THRESHOLD = 0.15


def _room_polygon(room) -> Polygon | None:  # noqa: ANN001
    pts = [(p.x, p.y) for p in room.polygon]
    poly = Polygon(pts)
    return poly if poly.is_valid and poly.area > 1e-6 else None


def find_room_overlaps(geometry: FloorPlanGeometry) -> list[ComplianceFlag]:
    """Erkennt sich ueberlappende Raumpolygone - das darf in einem echten
    Grundriss nie vorkommen und deutet auf einen Parsing-Fehler hin (z.B.
    ein Aussenbereich wie ein Balkon, der faelschlich innerhalb eines
    Innenraums platziert wurde).
    """
    flags: list[ComplianceFlag] = []
    polygons = [(room, _room_polygon(room)) for room in geometry.rooms]

    for i, (room_a, poly_a) in enumerate(polygons):
        if poly_a is None:
            continue
        for room_b, poly_b in polygons[i + 1 :]:
            if poly_b is None or not poly_a.intersects(poly_b):
                continue
            overlap_area = poly_a.intersection(poly_b).area
            smaller_area = min(poly_a.area, poly_b.area)
            if smaller_area <= 0 or overlap_area / smaller_area < _OVERLAP_RATIO_THRESHOLD:
                continue
            flags.append(
                ComplianceFlag(
                    severity="error",
                    standard="Geometrie-Konsistenz",
                    message=(
                        f"Räume '{room_a.name}' und '{room_b.name}' überlappen sich "
                        f"zu {overlap_area / smaller_area * 100:.0f}% - das kann in einem "
                        "echten Grundriss nicht vorkommen. Wahrscheinlich hat der Parser "
                        "einen Raum (z.B. Balkon) falsch positioniert."
                    ),
                    related_element_id=f"{room_a.id},{room_b.id}",
                )
            )
    return flags


def has_critical_errors(geometry: FloorPlanGeometry) -> bool:
    return any(f.severity == "error" for f in geometry.compliance_flags)
