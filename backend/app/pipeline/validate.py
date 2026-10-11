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

from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from app.models.schemas import ComplianceFlag, FloorPlanGeometry

# Ab diesem Anteil der kleineren Raumflaeche gilt eine Ueberlappung als
# gravierender Fehler (nicht nur Rundungstoleranz an einer gemeinsamen Wand).
_OVERLAP_RATIO_THRESHOLD = 0.15
_MIN_VALID_ROOM_AREA_M2 = 0.25
_ROOM_AREA_WARNING_RATIO = 0.20
_ROOM_AREA_ERROR_RATIO = 0.40


def _room_polygon(room) -> Polygon | None:  # noqa: ANN001
    pts = [(p.x, p.y) for p in room.polygon]
    if len(pts) < 3:
        return None
    poly = Polygon(pts)
    return poly if poly.is_valid and poly.area > 1e-6 else None


def validate_room_topology(geometry: FloorPlanGeometry) -> list[ComplianceFlag]:
    """Erweitert die reine Ueberlappungspruefung um geometrische Plausibilitaets-Checks.

    Die Topologie ist gerade bei komplexen Grundrissen der kritische Punkt: Ein
    Raum kann zwar nicht "ueberlappen", aber trotzdem ein nur knapp validiertes,
    selbstdurchschneidendes oder zu kleines Polygon liefern. Dieses Pruefset
    macht solche Fehler sichtbar, bevor sie als "huebscher 3D-Walkthrough"
    durchgehen.
    """
    flags: list[ComplianceFlag] = []
    seen_room_ids: set[str] = set()

    for room in geometry.rooms:
        if room.id in seen_room_ids:
            flags.append(
                ComplianceFlag(
                    severity="error",
                    standard="Raum-Topologie",
                    message=f"Raum-ID '{room.id}' ist nicht eindeutig.",
                    related_element_id=room.id,
                )
            )
        seen_room_ids.add(room.id)

        poly = _room_polygon(room)
        if poly is None:
            flags.append(
                ComplianceFlag(
                    severity="error",
                    standard="Raum-Topologie",
                    message=(
                        f"Raum '{room.name}' hat ein ungültiges oder zu kleines Polygon "
                        "und kann nicht als korrekte Innenraumfläche interpretiert werden."
                    ),
                    related_element_id=room.id,
                )
            )
            continue

        if poly.area < _MIN_VALID_ROOM_AREA_M2:
            flags.append(
                ComplianceFlag(
                    severity="warning",
                    standard="Raum-Topologie",
                    message=(
                        f"Raum '{room.name}' ist mit {poly.area:.2f} m² extrem klein; "
                        "das deutet auf eine fehlerhafte Polygon-Interpretation "
                        "oder eine unvollständige Raum-Detektion hin."
                    ),
                    related_element_id=room.id,
                )
            )

        if room.area_m2 is not None and room.area_m2 > 0:
            area_error = abs(poly.area - room.area_m2) / max(poly.area, room.area_m2)
            if area_error > _ROOM_AREA_WARNING_RATIO:
                severity = "error" if area_error > _ROOM_AREA_ERROR_RATIO else "warning"
                flags.append(
                    ComplianceFlag(
                        severity=severity,
                        standard="Raum-Topologie",
                        message=(
                            f"Raum '{room.name}' weicht zwischen Polygonfläche "
                            f"({poly.area:.2f} m²) und Planfläche ({room.area_m2:.2f} m²) "
                            f"um {area_error:.0%} ab. Die Geometrie muss vor der "
                            "Modellerzeugung geprüft werden."
                        ),
                        related_element_id=room.id,
                    )
                )

    for wall in geometry.walls:
        dx = wall.end.x - wall.start.x
        dy = wall.end.y - wall.start.y
        wall_length = (dx * dx + dy * dy) ** 0.5
        if wall_length <= 1e-6 or wall.thickness_m <= 0 or wall.height_m <= 0:
            flags.append(
                ComplianceFlag(
                    severity="error",
                    standard="Wand-Topologie",
                    message=f"Wand '{wall.id}' hat ungültige Länge, Stärke oder Höhe.",
                    related_element_id=wall.id,
                )
            )
            continue
        opening_end = 0.0
        for opening in sorted(wall.openings, key=lambda item: item.position_on_wall_m):
            if (
                opening.position_on_wall_m < 0
                or opening.width_m <= 0
                or opening.position_on_wall_m + opening.width_m > wall_length + 1e-3
                or opening.height_m <= 0
                or opening.sill_height_m < 0
                or opening.sill_height_m + opening.height_m > wall.height_m + 1e-3
            ):
                flags.append(
                    ComplianceFlag(
                        severity="error",
                        standard="Öffnungs-Topologie",
                        message=(
                            f"Öffnung in Wand '{wall.id}' liegt außerhalb der Wand "
                            "oder hat ungültige Abmessungen."
                        ),
                        related_element_id=wall.id,
                    )
                )
            if opening.position_on_wall_m < opening_end - 1e-3:
                flags.append(
                    ComplianceFlag(
                        severity="error",
                        standard="Öffnungs-Topologie",
                        message=f"Öffnungen in Wand '{wall.id}' überschneiden sich.",
                        related_element_id=wall.id,
                    )
                )
            opening_end = max(
                opening_end,
                opening.position_on_wall_m + opening.width_m,
            )

    rooms_by_id = {room.id: room for room in geometry.rooms}
    for item in geometry.furniture:
        room = rooms_by_id.get(item.room_id) if item.room_id else None
        if room is None:
            continue
        room_poly = _room_polygon(room)
        if room_poly is None:
            continue
        if not room_poly.buffer(0.1).covers(ShapelyPoint(item.center.x, item.center.y)):
            flags.append(
                ComplianceFlag(
                    severity="warning",
                    standard="Möbel-Topologie",
                    message=(
                        f"Der Mittelpunkt des Möbelstücks '{item.type.value}' liegt "
                        f"außerhalb des zugeordneten Raums '{room.name}'."
                    ),
                    related_element_id=room.id,
                )
            )

    flags.extend(find_room_overlaps(geometry))
    return flags


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
