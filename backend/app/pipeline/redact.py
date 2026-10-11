"""PII-Schwaerzung von Grundriss-Uploads VOR jeder Speicherung/Weiterverarbeitung.

Rechtlicher Hintergrund: Grundriss-Blaetter enthalten haeufig ein Schriftfeld
mit Architekt, Bauherr/Eigentuemer, Adresse, Telefon/E-Mail. Diese Datei
stellt sicher, dass solche Angaben geschwaerzt werden, BEVOR das Bild auf
Platte geschrieben oder an einen Parser-Provider geschickt wird - das
Original-Bild wird an keiner Stelle persistiert (siehe api/projects.py).

Architekturentscheidung, konsistent mit docs/ARCHITECTURE.md ("Grounding"-
Erkenntnis aus den Live-Tests): Pixelgenaue Textpositionen kommen von
klassischem OCR (Tesseract), NICHT von einem Vision-LLM - Vision-Modelle
sind nachweislich unzuverlässig bei pixelgenauen Koordinaten (siehe
backend/tests/fixtures/floorplans/FINDINGS.md). Die Klassifikation
"ist das ein Name/eine Adresse" uebernimmt eine lokale Keyword-/Regex-Logik
(laeuft komplett serverseitig, nichts verlaesst dafuer den Server).

WICHTIG - ehrliche Grenze: Das ist eine Best-Effort-Schwaerzung, KEINE
rechtlich garantierte Vollstaendigkeit. Kein automatisiertes System erkennt
100% aller Namen/PII zuverlaessig (z.B. ein frei im Bild stehender Name ohne
Label wie "Bauherr:" kann uebersehen werden). Fuer rechtlich sensible
Anwendungsfaelle ist eine manuelle Kontrollmoeglichkeit vor Weiterverarbeitung
zu ergaenzen (siehe docs/ARCHITECTURE.md Roadmap).
"""
from __future__ import annotations

import io
import re

import pytesseract
from PIL import Image, ImageDraw

# Schriftfeld-/Titelblock-Keywords (DACH-Baubranche): Wenn eine OCR-Zeile mit
# einem dieser Begriffe beginnt, wird die GESAMTE Zeile geschwaerzt (Label +
# Wert), da der Wert mit hoher Wahrscheinlichkeit ein Name/eine Firma ist.
_PII_LABEL_KEYWORDS = [
    "architekt", "architektin", "planverfasser", "bauherr", "bauherrin",
    "eigentuemer", "eigentümer", "auftraggeber", "ansprechpartner",
    "kontakt", "makler", "verkaeufer", "verkäufer", "vermieter",
    "projektleiter", "sachbearbeiter", "bearbeiter", "gezeichnet",
    "tel", "telefon", "fax", "e-mail", "email", "mobil",
]

# Typische Grundriss-Vokabeln, die trotz Grossschreibung KEINE Namen sind -
# verhindert, dass die generische "Zwei-Grossbuchstaben-Woerter"-Heuristik
# unten Raumbezeichnungen faelschlich schwaerzt.
_FLOORPLAN_VOCAB = {
    "wohnzimmer", "schlafzimmer", "kinderzimmer", "badezimmer", "bad", "wc",
    "kueche", "küche", "flur", "diele", "balkon", "terrasse", "keller",
    "garage", "treppenhaus", "treppe", "abstellraum", "hauswirtschaftsraum",
    "dachgeschoss", "erdgeschoss", "obergeschoss", "souterrain", "speicher",
    "grundriss", "massstab", "maßstab", "ansicht", "schnitt", "nordpfeil",
    "wohnkueche", "wohnküche", "esszimmer", "arbeitszimmer", "gaeste",
    "gäste", "windfang", "loggia", "abstellkammer", "waschkueche", "waschküche",
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d /()-]{6,}\d)")
_PLZ_CITY_RE = re.compile(r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+\b")
_STREET_RE = re.compile(r"\b[A-ZÄÖÜ][a-zäöüß]+(straße|strasse|weg|allee|platz|gasse)\s*\d+[a-z]?\b", re.IGNORECASE)
_NAME_WORD = r"(?:[A-ZÄÖÜ][a-zäöüß]{2,}|[A-ZÄÖÜ]{3,})"
_NAME_PAIR_RE = re.compile(rf"\b({_NAME_WORD})\s+({_NAME_WORD})\b")

_PADDING_PX = 4


def _is_floorplan_vocab(word: str) -> bool:
    return word.strip(".,:;-").lower() in _FLOORPLAN_VOCAB


def _line_is_pii(text: str) -> bool:
    lowered = text.lower()
    if any(lowered.startswith(kw) or f" {kw}" in lowered for kw in _PII_LABEL_KEYWORDS):
        return True
    if _EMAIL_RE.search(text):
        return True
    if _PHONE_RE.search(text):
        return True
    if _PLZ_CITY_RE.search(text):
        return True
    if _STREET_RE.search(text):
        return True
    for match in _NAME_PAIR_RE.finditer(text):
        first, last = match.group(1), match.group(2)
        if not _is_floorplan_vocab(first) and not _is_floorplan_vocab(last):
            return True
    return False


def redact_pii(image_bytes: bytes) -> bytes:
    """Nimmt die rohen Bild-Bytes entgegen (NICHT speichern!) und gibt
    geschwaerzte PNG-Bytes zurueck - das sind die einzigen Bytes, die
    anschliessend gespeichert oder an einen Parser-Provider geschickt werden
    duerfen.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    ocr_data = pytesseract.image_to_data(
        image, lang="deu+eng", output_type=pytesseract.Output.DICT
    )

    # OCR-Woerter zu Zeilen gruppieren (block/par/line-Index). Innerhalb
    # einer Tesseract-"Zeile" zusaetzlich nach horizontalem Abstand in
    # Cluster aufteilen: ein Raumlabel links im Plan und ein Schriftfeld
    # weit rechts koennen zufaellig auf derselben Hoehe/line_num liegen,
    # obwohl sie inhaltlich nichts miteinander zu tun haben - ohne diese
    # Aufteilung wuerde die Klassifikation "Zeile enthaelt PII" faelschlich
    # auch das unbeteiligte Raumlabel mit schwaerzen.
    raw_lines: dict[tuple[int, int, int], list[int]] = {}
    n = len(ocr_data["text"])
    for i in range(n):
        word = ocr_data["text"][i].strip()
        if not word:
            continue
        key = (ocr_data["block_num"][i], ocr_data["par_num"][i], ocr_data["line_num"][i])
        raw_lines.setdefault(key, []).append(i)

    lines: list[list[int]] = []
    for indices in raw_lines.values():
        indices.sort(key=lambda i: ocr_data["left"][i])
        cluster: list[int] = [indices[0]]
        for prev_i, cur_i in zip(indices, indices[1:]):
            prev_right = ocr_data["left"][prev_i] + ocr_data["width"][prev_i]
            gap = ocr_data["left"][cur_i] - prev_right
            avg_height = (ocr_data["height"][prev_i] + ocr_data["height"][cur_i]) / 2
            if gap > max(60, avg_height * 3):
                lines.append(cluster)
                cluster = []
            cluster.append(cur_i)
        lines.append(cluster)

    draw = ImageDraw.Draw(image)
    redacted_count = 0

    for indices in lines:
        line_text = " ".join(ocr_data["text"][i] for i in indices)
        if not _line_is_pii(line_text):
            continue
        xs0 = [ocr_data["left"][i] for i in indices]
        ys0 = [ocr_data["top"][i] for i in indices]
        xs1 = [ocr_data["left"][i] + ocr_data["width"][i] for i in indices]
        ys1 = [ocr_data["top"][i] + ocr_data["height"][i] for i in indices]
        box = (
            min(xs0) - _PADDING_PX,
            min(ys0) - _PADDING_PX,
            max(xs1) + _PADDING_PX,
            max(ys1) + _PADDING_PX,
        )
        draw.rectangle(box, fill=(20, 20, 20))
        redacted_count += 1

    # Strukturelle Zusatzsicherung: Unterschriften-/Stempelfelder (z.B. ein
    # Architekten-Logo) sind haeufig als STILISIERTE GRAFIK gerendert, nicht
    # als Text - OCR kann solche Logos grundsaetzlich nicht lesen und damit
    # auch nicht ueber die textbasierte Klassifikation oben erkennen. Deutsche
    # Bau-Titelbloecke haben dafuer aber eine verlaessliche Konvention: eine
    # "Ort, Datum"-Unterschriftszeile, direkt darueber der Platz fuer Name/
    # Stempel/Logo. Dieser Bereich wird vorsorglich IMMER geschwaerzt, auch
    # wenn OCR dort keinen Text erkannt hat.
    for indices in lines:
        line_text = " ".join(ocr_data["text"][i] for i in indices).lower()
        if "ort" not in line_text or "datum" not in line_text:
            continue
        block_num = ocr_data["block_num"][indices[0]]
        block_word_idxs = [
            i for i in range(n)
            if ocr_data["block_num"][i] == block_num and ocr_data["text"][i].strip()
        ]
        panel_left = min(ocr_data["left"][i] for i in block_word_idxs)
        panel_right = max(ocr_data["left"][i] + ocr_data["width"][i] for i in block_word_idxs)
        label_top = min(ocr_data["top"][i] for i in indices)
        signature_height = int(image.height * 0.14)
        box = (
            panel_left - _PADDING_PX,
            max(0, label_top - signature_height),
            panel_right + _PADDING_PX,
            label_top + _PADDING_PX,
        )
        draw.rectangle(box, fill=(20, 20, 20))
        redacted_count += 1

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
