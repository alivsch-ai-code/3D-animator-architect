"""Eingabe-Normalisierung: Makler laden Grundrisse haeufig als PDF hoch, nicht
als Bild. Alle Parser-Provider (parser.py) bekommen deshalb einheitlich ein
PNG - das vermeidet provider-spezifische PDF-Handhabung (nicht jedes
Vision-Modell/jeder API-Pfad akzeptiert PDFs gleich gut) und stellt sicher,
dass dasselbe Bild auch im Frontend angezeigt werden kann.
"""
from __future__ import annotations

import io

import pymupdf
from PIL import Image, ImageOps

PDF_RENDER_DPI = 200


def ensure_png(content: bytes, content_type: str | None, filename: str) -> tuple[bytes, str]:
    """Gibt (png_bytes, "image/png") zurueck - konvertiert PDFs (erste Seite),
    reicht Bilder ansonsten unveraendert als PNG durch (fuer konsistente
    Weiterverarbeitung/Anzeige).
    """
    is_pdf = (content_type == "application/pdf") or filename.lower().endswith(".pdf")

    if is_pdf:
        doc = pymupdf.open(stream=content, filetype="pdf")
        try:
            if doc.page_count == 0:
                raise ValueError("PDF enthaelt keine Seiten")
            page = doc.load_page(0)
            zoom = PDF_RENDER_DPI / 72.0
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            return pixmap.tobytes("png"), "image/png"
        finally:
            doc.close()

    with Image.open(io.BytesIO(content)) as source_image:
        image = ImageOps.exif_transpose(source_image).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"
