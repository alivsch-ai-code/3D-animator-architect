"""Pixelgenaue Grundriss-Geometrie per klassischer Bildverarbeitung.

Hintergrund (docs/ARCHITECTURE.md, Live-Tests 2026-10-11): Vision-LLMs lesen
Text (Raumnamen, Flaechen, Massstab) zuverlaessig, liefern aber keine exakten
Koordinaten ("Grounding"-Schwaeche) - Waende und Raumpolygone wichen
wiederholt vom Plan ab, z.B. ein Balkon innerhalb des Wohnzimmers. Daher die
Arbeitsteilung:

- Geometrie kommt ausschliesslich aus den Pixeln: Waende = dicke dunkle
  Balken (Schwellwert + morphologische Oeffnung entfernt Text, Masslinien,
  Moebelsymbole), Fenster-/Bruestungsluecken werden ueber die duennen
  Glas-/Gelaenderlinien im Original geschlossen, Raeume per Watershed auf der
  Wandabstands-Karte getrennt (Grenzen entstehen an Engstellen = Tueren).
- Bedeutung kommt aus Text: Startpunkte der Raeume sind die per OCR
  gefundenen Raumbeschriftungen (Abgleich mit den vom LLM erkannten Namen und
  Flaechen), der Massstab ergibt sich aus Pixel-Flaeche vs. beschrifteter
  Flaeche (Median ueber alle Raeume).

Gibt None zurueck, wenn der Plan sich dafuer nicht eignet (z.B. Handzeichnung,
fehlende Beschriftungen, inkonsistenter Massstab) - dann bleibt es bei der
LLM-Geometrie. Bekannte Grenzen: nur achsparallele Waende; schraffierte statt
gefuellte Waende werden nicht erkannt.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytesseract
from scipy import ndimage as ndi
from skimage.segmentation import watershed

from app.models.schemas import (
    ComplianceFlag,
    FloorPlanGeometry,
    FurnitureItem,
    Opening,
    OpeningType,
    Point2D,
    Room,
    RoomType,
    Wall,
)

_OUTSIDE = 1
_SHARED_SPACE_WORDS = {
    "treppenhaus", "treppe", "aufzug", "hausflur", "laubengang", "fahrstuhl",
    "staircase", "stairs", "stair", "elevator", "lift", "corridor", "lobby",
}
_AREA_RE = re.compile(r"^(\d{1,3})[.,](\d{1,2})")
_WINDOW_COVERAGE = 0.8
_SCALE_TOLERANCE = 0.15
_MIN_CONSISTENT_SHARE = 0.6


@dataclass
class _Word:
    text: str
    norm: str
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


@dataclass
class _Piece:
    axis: str  # "h" = horizontale Wand (Achse entlang x), "v" = vertikal
    c: float   # Lage quer zur Achse (y bei "h", x bei "v")
    a0: int    # Anfang entlang der Achse
    a1: int    # Ende entlang der Achse
    t: float   # Dicke in Pixeln


@dataclass
class _Gap:
    a0: int
    a1: int
    kind: str  # "window" | "door" | "open"


@dataclass
class _Line:
    axis: str
    c: float
    t: float
    a0: int
    a1: int
    gaps: list[_Gap] = field(default_factory=list)


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", folded)


def _parse_area(text: str) -> float | None:
    m = _AREA_RE.match(text.strip())
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def _ocr_words(gray: np.ndarray) -> list[_Word]:
    # Raumbeschriftungen sind auf Planblaettern oft nur ~15px hoch - erst ab
    # 2x Vergroesserung + "sparse text"-Modus findet Tesseract sie zuverlaessig.
    big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(
        big, lang="deu+eng", config="--psm 11", output_type=pytesseract.Output.DICT
    )
    words = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        words.append(
            _Word(
                text=text.strip(),
                norm=_norm(text),
                x=data["left"][i] // 2,
                y=data["top"][i] // 2,
                w=max(1, data["width"][i] // 2),
                h=max(1, data["height"][i] // 2),
            )
        )
    return words


def _numbers_below(word: _Word, words: list[_Word]) -> list[float]:
    values = []
    for other in words:
        if other is word:
            continue
        if not (word.y < other.y <= word.y + 4 * word.h):
            continue
        if not (word.x - word.w <= other.x <= word.x + 2 * word.w):
            continue
        value = _parse_area(other.text)
        if value is not None:
            values.append(value)
    return values


def _name_matches(word_norm: str, name_norm: str) -> bool:
    if not word_norm or not name_norm:
        return False
    if word_norm == name_norm:
        return True
    if len(word_norm) >= 4 and name_norm.startswith(word_norm):
        return True
    return len(word_norm) >= 4 and difflib.SequenceMatcher(None, word_norm, name_norm).ratio() >= 0.8


def _find_room_seed(room: Room, words: list[_Word]) -> tuple[int, int] | None:
    name_norm = _norm(room.name)
    best: tuple[float, _Word] | None = None
    for word in words:
        if not _name_matches(word.norm, name_norm):
            continue
        numbers = _numbers_below(word, words)
        score = 0.0
        if numbers:
            score = 1.0
            if room.area_m2 and any(abs(n - room.area_m2) <= 0.06 for n in numbers):
                score = 2.0
        if best is None or score > best[0]:
            best = (score, word)
    if best is not None:
        return best[1].center
    # Fallback: Raumname nicht lesbar, aber die beschriftete Flaeche schon.
    if room.area_m2:
        for word in words:
            value = _parse_area(word.text)
            if value is not None and abs(value - room.area_m2) <= 0.01:
                return word.center
    return None


def _wall_mask(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = int(min(max(otsu, 80), 170))
    dark = (gray < threshold).astype(np.uint8)
    k = max(3, round(min(gray.shape) / 330)) | 1
    walls = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    # Duenne Linien zusaetzlich ueber relativen Kontrast (Black-Hat): Glas- und
    # Gelaenderlinien sind in vielen Plaenen hellgrau statt schwarz und fallen
    # sonst durch einen absoluten Schwellwert.
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (k + 2, k + 2)))
    thin = ((dark == 1) | (blackhat > 30)).astype(np.uint8) & (1 - walls)
    return walls, thin, k


def _typical_wall_thickness(walls: np.ndarray) -> float:
    from skimage.morphology import skeletonize

    skeleton = skeletonize(walls.astype(bool))
    edt = ndi.distance_transform_edt(walls)
    widths = 2 * edt[skeleton]
    if widths.size == 0:
        return 0.0
    # 75. Perzentil: hoehere Perzentile werden von Wand-Kreuzungspunkten
    # (dort misst das Skelett die Diagonale der Kreuzung) nach oben verzerrt.
    return float(np.percentile(widths, 75))


def _roi(seeds: list[tuple[int, int]], shape: tuple[int, int]) -> tuple[int, int, int, int]:
    # Analyse nur im Umfeld der Raumbeschriftungen: Schriftfeld, Legende und
    # geschwaerzte Bereiche (dicke dunkle Balken) wuerden sonst als "Waende"
    # die Wandstaerken-Schaetzung und damit alle Schwellwerte verfaelschen.
    xs, ys = [s[0] for s in seeds], [s[1] for s in seeds]
    margin = int(max(0.6 * max(max(xs) - min(xs), max(ys) - min(ys)), 300))
    h, w = shape
    return (
        max(min(xs) - margin, 0),
        max(min(ys) - margin, 0),
        min(max(xs) + margin, w),
        min(max(ys) + margin, h),
    )


def _pieces(walls: np.ndarray, axis: str, min_len: int) -> list[_Piece]:
    kernel = (min_len, 1) if axis == "h" else (1, min_len)
    band = cv2.morphologyEx(walls, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(band, 8)
    pieces = []
    for i in range(1, count):
        x, y, w, h, _area = stats[i]
        mask = labels[y : y + h, x : x + w] == i
        if axis == "h":
            thickness = float(np.median(mask.sum(axis=0)))
            rows = np.nonzero(mask.any(axis=1))[0]
            pieces.append(_Piece("h", y + (rows.min() + rows.max()) / 2.0, x, x + w, thickness))
        else:
            thickness = float(np.median(mask.sum(axis=1)))
            cols = np.nonzero(mask.any(axis=0))[0]
            pieces.append(_Piece("v", x + (cols.min() + cols.max()) / 2.0, y, y + h, thickness))
    return pieces


def _has_door_swing(thin: np.ndarray, axis: str, c: float, a0: int, a1: int) -> bool:
    """Prueft auf einen Tuerschwenk-Bogen (Viertelkreis mit Radius = Lueckenbreite
    um eines der beiden Lueckenenden) - unterscheidet Tueren von offenen
    Durchgaengen und Fluren, die aehnlich breit sind."""
    gap = a1 - a0
    if gap < 5:
        return False
    h, w = thin.shape
    angles = np.linspace(0.15, np.pi / 2 - 0.15, 24)
    dilated = cv2.dilate(thin, np.ones((5, 5), np.uint8))
    # Das Tuerblatt ist oft etwas laenger als die gemessene Lichte (Anschlag
    # in der Leibung, Wandstummel neben der Zarge) - daher mehrere Radien;
    # nie kleiner als die Lichte (sonst passen fremde Boegen in Fluren).
    for radius in gap * np.array([1.0, 1.1, 1.2]):
        for hinge, toward in ((a0, 1), (a1, -1)):
            for side in (-1, 1):
                hits = 0
                for theta in angles:
                    along = hinge + toward * radius * np.cos(theta)
                    across = c + side * radius * np.sin(theta)
                    px, py = (along, across) if axis == "h" else (across, along)
                    xi, yi = int(round(px)), int(round(py))
                    if 0 <= yi < h and 0 <= xi < w and dilated[yi, xi]:
                        hits += 1
                if hits / len(angles) >= 0.3:
                    return True
    return False


def _gap_coverage(thin: np.ndarray, axis: str, c: float, t: float, a0: int, a1: int) -> float:
    # Band etwas breiter als die Wand: Gelaender/Bruestungen liegen oft an der
    # Aussenkante der Wandflucht statt mittig.
    lo, hi = int(c - t / 2) - 6, int(c + t / 2) + 7
    lo, hi = max(lo, 0), min(hi, thin.shape[0 if axis == "h" else 1])
    if a1 <= a0 or hi <= lo:
        return 0.0
    region = thin[lo:hi, a0:a1] if axis == "h" else thin[a0:a1, lo:hi].T
    return float(region.any(axis=0).mean())


def _cast_to_cross_wall(walls: np.ndarray, line: _Line, forward: bool, limit: int) -> tuple[int, int, int] | None:
    """Laeuft vom Linienende in Linienrichtung bis zur naechsten QUERwand.

    Gibt (Lueckenanfang, Lueckenende, Wandende) zurueck: Lueckenende = erstes Wandpixel nach
    der Luecke, Wandende = Position der Querwand. Beide unterscheiden sich,
    wenn vor der Querwand noch ein kurzes Wandstueck in derselben Flucht
    liegt (z.B. Wandecke ueber einer Balkontuer, kuerzer als ein eigenes
    Wandsegment) - das wird uebersprungen und der Linie zugeschlagen. Noetig
    fuer Luecken, die an einer senkrechten Wand enden statt an einem
    gleichgerichteten Wandstueck (Balkonbruestungen, Tueren in Raumecken)."""
    lo, hi = int(line.c - line.t / 2) + 1, int(line.c + line.t / 2)
    if hi <= lo:
        return None
    reach = int(line.t * 1.5) + 5
    size = walls.shape[1] if line.axis == "h" else walls.shape[0]
    cross = walls.shape[0] if line.axis == "h" else walls.shape[1]
    start = line.a1 if forward else line.a0 - 1
    step = 1 if forward else -1

    def band(pos: int) -> np.ndarray:
        return walls[lo:hi, pos] if line.axis == "h" else walls[pos, lo:hi]

    def is_cross(pos: int) -> bool:
        before = walls[max(lo - reach, 0):lo, pos] if line.axis == "h" else walls[pos, max(lo - reach, 0):lo]
        after = walls[hi:min(hi + reach, cross), pos] if line.axis == "h" else walls[pos, hi:min(hi + reach, cross)]
        return before.mean() > 0.6 or after.mean() > 0.6

    # Die Linie (aus der morphologischen Oeffnung) endet oft 1-2 px vor dem
    # Rand der Rohmaske - diese Restpixel gehoeren noch zur Wand.
    for _ in range(int(line.t)):
        if 0 <= start < size and band(start).mean() >= 0.5:
            start += step
        else:
            break
    gap_start = start
    for i in range(limit):
        pos = start + step * i
        if pos < 0 or pos >= size:
            return None
        if band(pos).mean() < 0.5:
            continue
        if i < 3:
            return None
        gap_end = pos
        for j in range(int(3 * line.t) + 10):
            q = gap_end + step * j
            if q < 0 or q >= size or band(q).mean() < 0.5:
                return None
            if is_cross(q):
                return gap_start, gap_end, q
        return None
    return None


def _classify_gap(thin: np.ndarray, marks: np.ndarray, axis: str, c: float, t: float, g0: int, g1: int,
                  door_max: float, gap_max: float, require_swing: bool) -> str:
    width = g1 - g0
    # Fenster/Bruestung: die Wandflucht ist im Original durchgehend mit Rahmen-,
    # Glas- oder Gelaenderlinien gefuellt (marks = duenne Linien + duenne
    # "Wandstuecke" wie Fensterrahmen).
    if width <= gap_max and _gap_coverage(marks, axis, c, t, g0, g1) >= _WINDOW_COVERAGE:
        return "window"
    # Tuer nur mit erkennbarem Schwenkbogen - ohne diese Pruefung wurden Flure
    # (aehnlich breit wie Tueren) als "Tuer quer durch den Flur" erkannt.
    if width <= door_max and (not require_swing or _has_door_swing(thin, axis, c, g0, g1)):
        return "door"
    return "open"


def _extend_ends(lines: list[_Line], walls: np.ndarray, thin: np.ndarray, marks: np.ndarray,
                 door_max: float, gap_max: float) -> None:
    for line in lines:
        for forward in (True, False):
            hit = _cast_to_cross_wall(walls, line, forward, int(gap_max))
            if hit is None:
                continue
            gap_start, gap_end, wall_end = hit
            g0, g1 = (gap_start, gap_end) if forward else (gap_end + 1, gap_start + 1)
            if g1 - g0 < 3:
                continue
            # Am Linienende (Luecke bis zur Querwand) ist der Schwenkbogen Pflicht:
            # sonst wuerde jeder Flur, der auf eine Wand zulaeuft, zur "Tuer".
            kind = _classify_gap(thin, marks, line.axis, line.c, line.t, g0, g1, door_max, gap_max, True)
            if kind == "open":
                continue
            line.gaps.append(_Gap(g0, g1, kind))
            line.gaps.sort(key=lambda g: g.a0)
            line.a0, line.a1 = min(line.a0, g0, wall_end), max(line.a1, g1, wall_end + 1)


def _lines(pieces: list[_Piece], thin: np.ndarray, marks: np.ndarray, door_max: float,
           gap_max: float) -> list[_Line]:
    lines: list[_Line] = []
    for axis in ("h", "v"):
        group = sorted((p for p in pieces if p.axis == axis), key=lambda p: (p.c, p.a0))
        clusters: list[list[_Piece]] = []
        for piece in group:
            for cluster in clusters:
                ref = max(cluster, key=lambda p: p.t)
                if abs(ref.c - piece.c) <= max(ref.t, piece.t) * 0.5:
                    cluster.append(piece)
                    break
            else:
                clusters.append([piece])
        for cluster in clusters:
            # Sehr duenne Stuecke in der Flucht einer dicken Wand sind
            # Fensterrahmen, keine Wand - sie fuellen die Luecke (siehe marks).
            t_ref = max(p.t for p in cluster)
            cluster = sorted((p for p in cluster if p.t >= 0.35 * t_ref), key=lambda p: p.a0)
            c = float(np.mean([p.c for p in cluster]))
            t = float(np.median([p.t for p in cluster]))
            line = _Line(axis, c, t, cluster[0].a0, cluster[0].a1)
            for piece in cluster[1:]:
                gap = piece.a0 - line.a1
                if gap <= 0.8 * t:
                    line.a1 = max(line.a1, piece.a1)
                    continue
                # Zwischen zwei Wandstuecken derselben Flucht ist eine tuerbreite
                # Luecke praktisch immer eine Tuer - Schwenkboegen sind in
                # manchen Plaenen zu blass/gestrichelt fuer eine sichere Erkennung.
                kind = _classify_gap(thin, marks, axis, c, t, line.a1, piece.a0, door_max, gap_max, False)
                if kind == "open":
                    lines.append(line)
                    line = _Line(axis, c, t, piece.a0, piece.a1)
                    continue
                line.gaps.append(_Gap(line.a1, piece.a0, kind))
                line.a1 = piece.a1
            lines.append(line)
    return lines


def _climb_to_room_center(dist: np.ndarray, x: int, y: int, max_travel: float) -> tuple[int, int]:
    # Beschriftungen stehen oft nah an einer Wand - von dort wuerde der
    # Watershed gegen Nachbarraeume verlieren, die ueber die Tuer in die
    # tiefere Raummitte "fliessen". Daher Bergsteigen zum lokalen Maximum des
    # Wandabstands (bleibt per Konstruktion im freien Raum, kreuzt keine Wand).
    # max_travel begrenzt den Weg: bei einem zur Seite offenen Raum (z.B.
    # Balkon mit nicht erkannter Bruestung) wuerde der Anstieg sonst ins Freie
    # hinauslaufen.
    h, w = dist.shape
    x_start, y_start = x, y
    for _ in range(2000):
        if (x - x_start) ** 2 + (y - y_start) ** 2 > max_travel**2:
            break
        y0, y1, x0, x1 = max(y - 2, 0), min(y + 3, h), max(x - 2, 0), min(x + 3, w)
        window = dist[y0:y1, x0:x1]
        dy, dx = np.unravel_index(int(np.argmax(window)), window.shape)
        ny, nx = y0 + dy, x0 + dx
        if dist[ny, nx] <= dist[y, x]:
            break
        x, y = nx, ny
    return x, y


def _room_polygon(region: np.ndarray, ppm: float) -> list[tuple[float, float]] | None:
    filled = ndi.binary_fill_holes(region).astype(np.uint8)
    contours, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    approx = cv2.approxPolyDP(contour, 0.04 * ppm, True)
    if len(approx) < 3:
        return None
    return [(float(p[0][0]), float(p[0][1])) for p in approx]


def _label_at(labels: np.ndarray, x: float, y: float) -> int:
    xi, yi = int(round(x)), int(round(y))
    if 0 <= yi < labels.shape[0] and 0 <= xi < labels.shape[1]:
        return int(labels[yi, xi])
    return _OUTSIDE


def _clip_line_to_unit(line: _Line, unit: np.ndarray) -> tuple[int, int] | None:
    reach = int(line.t / 2 + 4)
    lo, hi = int(line.c) - reach, int(line.c) + reach + 1
    if line.axis == "h":
        lo, hi = max(lo, 0), min(hi, unit.shape[0])
        band = unit[lo:hi, line.a0 : line.a1]
        touched = band.any(axis=0)
    else:
        lo, hi = max(lo, 0), min(hi, unit.shape[1])
        band = unit[line.a0 : line.a1, lo:hi]
        touched = band.any(axis=1)
    idx = np.nonzero(touched)[0]
    if idx.size < 3:
        return None
    margin = int(line.t / 2 + 1)
    return max(line.a0, line.a0 + int(idx.min()) - margin), min(line.a1, line.a0 + int(idx.max()) + 1 + margin)


def refine_geometry_with_cv(image_bytes: bytes, llm: FloorPlanGeometry) -> FloorPlanGeometry | None:
    """Ersetzt Waende/Raumpolygone der LLM-Geometrie durch pixelgenaue
    Bildanalyse-Ergebnisse. Namen, Typen, Flaechenangaben, Moebeltypen und
    Normhinweise bleiben vom LLM. Gibt None zurueck, wenn die Bildanalyse
    nicht verlaesslich ist."""
    if not llm.rooms:
        return None
    full_gray = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if full_gray is None:
        return None

    words_full = _ocr_words(full_gray)
    seeds_full: dict[str, tuple[int, int]] = {}
    for room in llm.rooms:
        seed = _find_room_seed(room, words_full)
        if seed is None:
            return None
        seeds_full[room.id] = seed
    if len(seeds_full) < 2:
        return None

    rx0, ry0, rx1, ry1 = _roi(list(seeds_full.values()), full_gray.shape)
    gray = full_gray[ry0:ry1, rx0:rx1]
    words = [
        _Word(w.text, w.norm, w.x - rx0, w.y - ry0, w.w, w.h)
        for w in words_full
        if rx0 <= w.x < rx1 and ry0 <= w.y < ry1
    ]

    walls, thin, _k = _wall_mask(gray)
    t_max = _typical_wall_thickness(walls)
    if t_max < 3:
        return None
    door_max = 4.0 * t_max
    gap_max = 18.0 * t_max
    # Mindestlaenge > Wandstaerke, sonst "ueberlebt" eine sehr dicke Wand
    # (z.B. doppelte Wohnungstrennwand) auch die Oeffnung in Querrichtung.
    min_len = int(max(2.0 * t_max, 15))

    pieces = _pieces(walls, "h", min_len) + _pieces(walls, "v", min_len)
    marks = thin | walls
    lines = _lines(pieces, thin, marks, door_max, gap_max)
    _extend_ends(lines, walls, thin, marks, door_max, gap_max)

    closed = walls.copy()
    for line in lines:
        for gap in line.gaps:
            if gap.kind != "window":
                continue
            lo, hi = int(line.c - line.t / 2), int(line.c + line.t / 2) + 1
            if line.axis == "h":
                closed[lo:hi, gap.a0 : gap.a1] = 1
            else:
                closed[gap.a0 : gap.a1, lo:hi] = 1
    free = closed == 0
    dist = ndi.distance_transform_edt(free)

    markers = np.zeros(gray.shape, np.int32)
    border = np.zeros(gray.shape, bool)
    border[:3, :] = border[-3:, :] = True
    border[:, :3] = border[:, -3:] = True
    markers[border & free] = _OUTSIDE

    max_travel = 2.0 * door_max
    room_ids: dict[str, int] = {}
    next_id = 2
    for room in llm.rooms:
        sx, sy = seeds_full[room.id]
        x, y = _climb_to_room_center(dist, sx - rx0, sy - ry0, max_travel)
        if not free[y, x]:
            return None
        cv2.circle(markers, (x, y), max(2, int(dist[y, x] * 0.5)), next_id, -1)
        room_ids[room.id] = next_id
        next_id += 1

    # Konkurrierende Startpunkte fuer Gemeinschaftsflaechen/Nachbarwohnungen,
    # damit z.B. der Flur der Wohnung nicht ueber die Wohnungstuer in Treppen-
    # haus und Nachbareinheiten "ausläuft".
    for word in words:
        if word.norm in _SHARED_SPACE_WORDS:
            x, y = _climb_to_room_center(dist, *word.center, max_travel)
            if free[y, x] and markers[y, x] == 0:
                cv2.circle(markers, (x, y), max(2, int(dist[y, x] * 0.5)), next_id, -1)
                next_id += 1
    markers[~free] = 0

    labels = watershed(-dist, markers, mask=free)

    rooms_by_id = {room.id: room for room in llm.rooms}
    regions = {room_id: labels == label for room_id, label in room_ids.items()}

    ratios = {}
    for room_id, region in regions.items():
        area = rooms_by_id[room_id].area_m2
        if area and area > 0 and region.sum() > 0:
            ratios[room_id] = float(np.sqrt(region.sum() / area))
    if len(ratios) < 2:
        return None
    ppm = float(np.median(list(ratios.values())))
    consistent = [r for r, v in ratios.items() if abs(v / ppm - 1) <= _SCALE_TOLERANCE]
    if len(consistent) < max(2, _MIN_CONSISTENT_SHARE * len(ratios)):
        return None

    unit = np.zeros(gray.shape, bool)
    for region in regions.values():
        unit |= region
    ys, xs = np.nonzero(unit)
    ox, oy = float(xs.min()), float(ys.min())

    def to_m(px: float, py: float) -> Point2D:
        return Point2D(x=round((px - ox) / ppm, 3), y=round((py - oy) / ppm, 3))

    flags: list[ComplianceFlag] = []
    new_rooms: list[Room] = []
    for room in llm.rooms:
        polygon = _room_polygon(regions[room.id], ppm)
        if polygon is None:
            return None
        if room.id not in consistent:
            measured = regions[room.id].sum() / ppm**2
            flags.append(
                ComplianceFlag(
                    severity="warning",
                    standard="Geometrie-Bildanalyse",
                    message=(
                        f"Raum '{room.name}': gemessene Flaeche {measured:.1f} m² weicht von der "
                        f"Planbeschriftung ({room.area_m2} m²) ab - Raumgrenze bitte pruefen."
                    ),
                    related_element_id=room.id,
                )
            )
        new_rooms.append(room.model_copy(update={"polygon": [to_m(x, y) for x, y in polygon]}))

    room_label_ids = set(room_ids.values())
    balcony_labels = {
        room_ids[r.id] for r in llm.rooms if r.type == RoomType.balcony and r.id in room_ids
    }
    wall_height = float(np.median([w.height_m for w in llm.walls])) if llm.walls else 2.5

    def side_labels(line: _Line, a: float) -> tuple[int, int]:
        off = line.t / 2 + 4
        if line.axis == "h":
            return _label_at(labels, a, line.c - off), _label_at(labels, a, line.c + off)
        return _label_at(labels, line.c - off, a), _label_at(labels, line.c + off, a)

    def make_wall(line: _Line, a0: float, a1: float, wid: str, height: float, thickness: float,
                  openings: list[Opening]) -> Wall:
        if line.axis == "h":
            start, end = to_m(a0, line.c), to_m(a1, line.c)
        else:
            start, end = to_m(line.c, a0), to_m(line.c, a1)
        mid_sides = side_labels(line, (a0 + a1) / 2)
        return Wall(
            id=wid,
            start=start,
            end=end,
            thickness_m=round(thickness / ppm, 3),
            height_m=height,
            is_exterior=_OUTSIDE in mid_sides,
            openings=openings,
        )

    new_walls: list[Wall] = []
    for line in lines:
        clipped = _clip_line_to_unit(line, unit)
        if clipped is None:
            continue
        a0, a1 = clipped
        # Frei im Raum stehende "Wand" (beidseitig derselbe Raum) ist in der
        # Praxis ein dunkel gefuelltes Moebelstueck (z.B. Sideboard), keine Wand.
        samples = [side_labels(line, a0 + f * (a1 - a0)) for f in (0.25, 0.5, 0.75)]
        if all(left == right and left in room_label_ids for left, right in samples):
            continue
        segment_start = a0
        openings: list[Opening] = []
        for gap in line.gaps:
            if gap.a1 <= a0 or gap.a0 >= a1:
                continue
            g0, g1 = max(gap.a0, a0), min(gap.a1, a1)
            sides = set(side_labels(line, (g0 + g1) / 2))
            if not sides & room_label_ids:
                continue
            # Verglaste Oeffnung zwischen Innenraum und Balkon = Balkontuer.
            if gap.kind == "window" and sides & balcony_labels and (sides - balcony_labels) & room_label_ids:
                gap = _Gap(gap.a0, gap.a1, "door")
            if gap.kind == "window" and sides & balcony_labels and _OUTSIDE in sides:
                # Balkon-Bruestung: als eigene niedrige Wand statt Fenster.
                if g0 > segment_start:
                    new_walls.append(make_wall(line, segment_start, g0, f"cv{len(new_walls)}",
                                               wall_height, line.t, openings))
                new_walls.append(make_wall(line, g0, g1, f"cv{len(new_walls)}", 1.0,
                                           max(line.t * 0.3, 0.08 * ppm), []))
                openings = []
                segment_start = g1
                continue
            width = (g1 - g0) / ppm
            position = (g0 - segment_start) / ppm
            if gap.kind == "window":
                openings.append(Opening(type=OpeningType.window, position_on_wall_m=round(position, 3),
                                        width_m=round(width, 3), height_m=1.3, sill_height_m=0.9))
            elif gap.kind == "door":
                openings.append(Opening(type=OpeningType.door, position_on_wall_m=round(position, 3),
                                        width_m=round(width, 3), height_m=2.1, sill_height_m=0.0))
        if a1 > segment_start:
            new_walls.append(make_wall(line, segment_start, a1, f"cv{len(new_walls)}",
                                       wall_height, line.t, openings))

    if len(new_walls) < 3:
        return None

    new_room_by_id = {room.id: room for room in new_rooms}
    new_furniture: list[FurnitureItem] = []
    for item in llm.furniture:
        old_room = rooms_by_id.get(item.room_id) if item.room_id else None
        new_room = new_room_by_id.get(item.room_id) if item.room_id else None
        if old_room is None or new_room is None:
            continue
        ox0, oy0 = min(p.x for p in old_room.polygon), min(p.y for p in old_room.polygon)
        ox1, oy1 = max(p.x for p in old_room.polygon), max(p.y for p in old_room.polygon)
        nx0, ny0 = min(p.x for p in new_room.polygon), min(p.y for p in new_room.polygon)
        nx1, ny1 = max(p.x for p in new_room.polygon), max(p.y for p in new_room.polygon)
        u = (item.center.x - ox0) / (ox1 - ox0) if ox1 > ox0 else 0.5
        v = (item.center.y - oy0) / (oy1 - oy0) if oy1 > oy0 else 0.5
        u, v = min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)
        center = Point2D(x=round(nx0 + u * (nx1 - nx0), 3), y=round(ny0 + v * (ny1 - ny0), 3))
        new_furniture.append(item.model_copy(update={"center": center}))

    flags.append(
        ComplianceFlag(
            severity="info",
            standard="Geometrie-Bildanalyse",
            message=(
                f"Waende und Raumgrenzen pixelgenau per Bildanalyse aus dem Grundriss extrahiert "
                f"(Massstab aus beschrifteten Raumflaechen: {ppm:.1f} px/m, "
                f"{len(consistent)}/{len(ratios)} Raeume massstabskonsistent)."
            ),
            related_element_id=None,
        )
    )

    return llm.model_copy(
        update={
            "walls": new_walls,
            "rooms": new_rooms,
            "furniture": new_furniture,
            "compliance_flags": [*llm.compliance_flags, *flags],
        }
    )
