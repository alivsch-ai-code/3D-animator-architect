"""Leitet Raumpolygone DETERMINISTISCH aus dem Wand-Liniennetz ab, statt den
vom Parser unabhaengig gelieferten Raumpolygon-Koordinaten blind zu vertrauen.

Hintergrund (siehe docs/ARCHITECTURE.md "Live-Testergebnis" 2026-10-11): Ein
Live-Bug zeigte, dass ein Vision-LLM (auch ein starkes wie Claude Opus 4.6)
Waende UND Raumpolygone weitgehend UNABHAENGIG voneinander generiert - beide
muessen rein "zufaellig" uebereinstimmen. In einem Testfall wurde ein Balkon
wiederholt (systematisch, nicht nur einmalig) INNERHALB des Wohnzimmer-
Polygons platziert statt ausserhalb der Fassade.

Loesung (per Recherche bestaetigt, u.a. Raster-to-Vector/Liu et al. ICCV 2017
und die CubiCasa5K-eigene Ground-Truth-Pipeline nutzen denselben Grundgedanken
"Raum = eingeschlossene Flaeche des Wandnetzes"): Waende werden als 2D-Masse
(Mittellinie + echte Wandstaerke) aufgebaut und vereinigt; die eingeschlossenen
Leerraeume (Gebaeudegrundriss minus Wandmasse) SIND per Konstruktion bereits
ueberlappungsfrei - eine mathematische Garantie, keine gelernte/gehoffte
Eigenschaft. Das LLM muss dann nur noch einen Raum anhand eines Punkts in
seinem (ggf. ungenauen) Original-Polygon einer der abgeleiteten Flaechen
zuordnen ("Labeling") statt pixelgenaue Polygon-Koordinaten zu erraten - eine
deutlich fehlertolerantere Aufgabe.

Tueren/Fenster werden bewusst NICHT als Luecke im Wandnetz behandelt (eine
Tuer darf eine Raumgrenze nicht aufbrechen) - die Wandmittellinie wird
unabhaengig von geometry.py::Wall.openings als durchgehend betrachtet.
"""
from __future__ import annotations

from shapely.geometry import LineString
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import polygonize, unary_union

from app.models.schemas import ComplianceFlag, FloorPlanGeometry, Point2D, Wall
from app.pipeline.validate import find_room_overlaps

_MIN_VOID_AREA_M2 = 0.5
_FALLBACK_FOOTPRINT_BUFFER_M = 0.3
# Ein abgeleiteter Raum-Void darf flaechenmaessig max. um diesen Faktor vom
# urspruenglich deklarierten area_m2 abweichen - sonst ist der "Treffer"
# vermutlich ein Artefakt unsauberer Wandverbindungen (z.B. zwei Raeume durch
# eine Luecke faelschlich zu einem Void verschmolzen) und wird verworfen.
_MAX_AREA_RATIO = 1.6
_MIN_AREA_RATIO = 0.6
# Gesamtflaeche aller Raeume darf sich durch die Ableitung nur um diesen
# Anteil veraendern - ein groesserer Sprung deutet auf fehlerhaft
# verschmolzene/aufgeteilte Voids hin (z.B. durch eine Wandluecke), auch wenn
# die reine Ueberlappungs-ANZAHL dabei zufaellig gleich bleibt.
_MAX_TOTAL_AREA_DRIFT = 0.15


def _wall_centerline(wall: Wall) -> LineString | None:
    line = LineString([(wall.start.x, wall.start.y), (wall.end.x, wall.end.y)])
    return line if line.length > 1e-6 else None


# Live-Test an echten Daten zeigte: Parser-Koordinaten fuer anstossende Waende
# sind nicht immer konsequent auf dieselbe Referenz bezogen - z.B. beginnt
# eine Innenwand teils an der INNENKANTE einer Aussenwand (volle Wandstaerke
# vom Mittellinien-Ursprung entfernt) statt an deren Mittellinie. Ohne
# Ausgleich entsteht dort eine Luecke in der Wandmasse, durch die zwei
# eigentlich getrennte Raum-Voids zu einem einzigen grossen verschmelzen
# (beobachtet: 7 korrekte Raeume wurden zu einem 87m²-Monster-Void). Fix:
# jede Wandlinie wird vor dem Puffern an beiden Enden etwas verlaengert, das
# schliesst diese Luecken an T-Stuecken/Ecken zuverlaessig.
_JUNCTION_TOLERANCE_M = 0.25


def _extend_line(line: LineString, amount: float) -> LineString:
    (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
    dx, dy = x1 - x0, y1 - y0
    length = (dx**2 + dy**2) ** 0.5
    if length < 1e-9:
        return line
    ux, uy = dx / length, dy / length
    return LineString(
        [(x0 - ux * amount, y0 - uy * amount), (x1 + ux * amount, y1 + uy * amount)]
    )


def _wall_mass(wall: Wall) -> ShapelyPolygon | None:
    line = _wall_centerline(wall)
    if line is None:
        return None
    half_thickness = max(wall.thickness_m, 0.02) / 2.0
    extended = _extend_line(line, _JUNCTION_TOLERANCE_M)
    # cap_style="square": Puffer reicht ueber die Linienenden hinaus - schliesst
    # Ecken/T-Stoesse zuverlaessiger als "flat", minimal grosszuegigere
    # Eckgeometrie wird beim Vereinigen aller Waende irrelevant.
    return extended.buffer(half_thickness, cap_style="square")


def _building_footprint(geometry: FloorPlanGeometry) -> ShapelyPolygon | None:
    exterior_lines = [
        _wall_centerline(w) for w in geometry.walls if w.is_exterior
    ]
    exterior_lines = [line for line in exterior_lines if line is not None]
    if exterior_lines:
        candidates = list(polygonize(exterior_lines))
        if candidates:
            footprint = max(candidates, key=lambda p: p.area)
            if footprint.area > 1.0:
                return footprint

    # Fallback: Aussenwaende bilden keinen geschlossenen Ring (z.B. Luecke
    # im Parsing) - Vereinigung der vom Parser gelieferten Raumpolygone,
    # leicht nach aussen gepuffert, als grobe Ersatz-Aussenkontur.
    room_polys = []
    for room in geometry.rooms:
        pts = [(p.x, p.y) for p in room.polygon]
        if len(pts) >= 3:
            poly = ShapelyPolygon(pts)
            if poly.is_valid and poly.area > 1e-6:
                room_polys.append(poly)
    if not room_polys:
        return None
    return unary_union(room_polys).buffer(_FALLBACK_FOOTPRINT_BUFFER_M)


def derive_room_polygons(geometry: FloorPlanGeometry) -> FloorPlanGeometry:
    """Ersetzt Raumpolygone durch deterministisch aus dem Wandnetz abgeleitete
    Flaechen, wo moeglich. Raeume, die sich nicht eindeutig zuordnen lassen
    (z.B. ein Balkon ohne vollstaendig umschliessende Waende), behalten ihre
    urspruengliche Parser-Geometrie - mit einem erklaerenden compliance_flag.
    """
    wall_masses = [m for w in geometry.walls if (m := _wall_mass(w)) is not None]
    if not wall_masses:
        return geometry

    footprint = _building_footprint(geometry)
    if footprint is None:
        return geometry

    wall_mass_union = unary_union(wall_masses)
    voids = footprint.difference(wall_mass_union)
    void_polys = [g for g in getattr(voids, "geoms", [voids]) if g.area > _MIN_VOID_AREA_M2]

    used_void_indices: set[int] = set()
    match_by_room_id: dict[str, int] = {}

    def _area_plausible(void_area: float, declared_area: float | None) -> bool:
        if not declared_area:
            return True  # kein Vergleichswert vorhanden - nicht blockieren
        ratio = void_area / declared_area
        return _MIN_AREA_RATIO <= ratio <= _MAX_AREA_RATIO

    # Pass 1: Punkt-in-Polygon ueber einen repraesentativen Punkt des
    # ORIGINAL-Parserpolygons. Funktioniert gut, wenn die ungefaehre Position
    # stimmt (z.B. leicht ungenaue Konturen), versagt aber genau in dem Fall,
    # der diesen Mechanismus ueberhaupt noetig macht: ein Raum, der komplett
    # an der falschen Stelle platziert wurde (siehe Pass 2). Zusaetzlich
    # Flaechen-Plausibilitaet pruefen - sonst wuerde z.B. ein durch eine
    # Wandluecke mit dem Nachbarraum verschmolzener Riesen-Void akzeptiert.
    for room in geometry.rooms:
        orig_pts = [(p.x, p.y) for p in room.polygon]
        orig_poly = ShapelyPolygon(orig_pts) if len(orig_pts) >= 3 else None
        if orig_poly is None or not orig_poly.is_valid or orig_poly.is_empty:
            continue
        # representative_point() statt centroid(): bei konkaven/L-foermigen
        # Polygonen liegt der Centroid u.U. AUSSERHALB der Flaeche.
        label_point = orig_poly.representative_point()
        for i, void in enumerate(void_polys):
            if i in used_void_indices:
                continue
            if void.contains(label_point) and _area_plausible(void.area, room.area_m2):
                match_by_room_id[room.id] = i
                used_void_indices.add(i)
                break

    # Pass 2: Fallback ueber Flaechenaehnlichkeit fuer Raeume, deren Original-
    # Position komplett falsch war (Pass 1 fand keinen Treffer) - die vom
    # Parser genannte FLAECHE ist erfahrungsgemaess auch bei falscher
    # Position oft noch brauchbar (siehe Live-Testdaten), da sie meist direkt
    # aus der Plan-Beschriftung uebernommen wird, nicht geometrisch erraten.
    unmatched_rooms = [r for r in geometry.rooms if r.id not in match_by_room_id and r.area_m2]
    unclaimed_void_idxs = [i for i in range(len(void_polys)) if i not in used_void_indices]
    for room in sorted(unmatched_rooms, key=lambda r: r.area_m2 or 0):
        if not unclaimed_void_idxs:
            break
        best_i = min(unclaimed_void_idxs, key=lambda i: abs(void_polys[i].area - room.area_m2))
        if _area_plausible(void_polys[best_i].area, room.area_m2):
            match_by_room_id[room.id] = best_i
            unclaimed_void_idxs.remove(best_i)

    updated_rooms = []
    extra_flags: list[ComplianceFlag] = []
    for room in geometry.rooms:
        match_idx = match_by_room_id.get(room.id)
        if match_idx is not None:
            new_poly = void_polys[match_idx]
            coords = list(new_poly.exterior.coords)[:-1]
            room = room.model_copy(
                update={
                    "polygon": [Point2D(x=x, y=y) for x, y in coords],
                    "area_m2": round(new_poly.area, 2),
                }
            )
        else:
            extra_flags.append(
                ComplianceFlag(
                    severity="info",
                    standard="Geometrie-Ableitung",
                    message=(
                        f"Raum '{room.name}' konnte nicht eindeutig aus dem Wandnetz "
                        "abgeleitet werden (z.B. nicht vollstaendig umschlossen, etwa "
                        "ein Balkon ohne durchgehende Bruestung) - urspruengliche "
                        "Parser-Geometrie wurde beibehalten."
                    ),
                    related_element_id=room.id,
                )
            )

        updated_rooms.append(room)

    corrected = geometry.model_copy(
        update={
            "rooms": updated_rooms,
            "compliance_flags": [*geometry.compliance_flags, *extra_flags],
        }
    )

    # Sicherheitsnetz: Die Ableitung wird nur uebernommen, wenn sie die Lage
    # nachweislich NICHT verschlechtert. Zwei unabhaengige Pruefungen, weil
    # keine allein ausreicht - beobachtet an echten Testdaten (siehe
    # docs/ARCHITECTURE.md): die reine Ueberlappungs-ANZAHL kann trotz falsch
    # verschobener Raumgrenzen gleich bleiben (z.B. wenn eine Wandluecke
    # Raeume falsch zusammenlegt, ohne dass das Ergebnis technisch
    # "ueberlappt").
    # 1. Darf nicht MEHR Ueberlappungen erzeugen als vorher.
    # 2. Die Gesamtflaeche aller Raeume darf sich nicht stark veraendern -
    #    reale Grundflaeche aendert sich durch eine reine Neuzuordnung nicht.
    if len(find_room_overlaps(corrected)) > len(find_room_overlaps(geometry)):
        return geometry

    orig_total = sum(r.area_m2 or 0 for r in geometry.rooms)
    corrected_total = sum(r.area_m2 or 0 for r in corrected.rooms)
    if orig_total > 0:
        drift = abs(corrected_total - orig_total) / orig_total
        if drift > _MAX_TOTAL_AREA_DRIFT:
            return geometry

    return corrected
