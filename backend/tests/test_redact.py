import io

from PIL import Image, ImageDraw, ImageFont

from app.pipeline.redact import redact_pii


def _make_test_image() -> bytes:
    img = Image.new("RGB", (900, 300), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=20)
    except Exception:
        font = ImageFont.load_default()

    d.text((20, 20), "Wohnzimmer", fill="black", font=font)
    d.text((20, 60), "Kueche", fill="black", font=font)
    d.text((20, 100), "Massstab 1:100", fill="black", font=font)

    d.text((500, 20), "Architekt: Max Mustermann", fill="black", font=font)
    d.text((500, 60), "Bauherr: Erika Musterfrau", fill="black", font=font)
    d.text((500, 100), "Tel: 030 1234567", fill="black", font=font)
    d.text((500, 140), "max.mustermann@example.com", fill="black", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _count_dark_pixels(image_bytes: bytes, box: tuple[int, int, int, int]) -> int:
    img = Image.open(io.BytesIO(image_bytes)).convert("L").crop(box)
    return sum(1 for px in img.getdata() if px < 60)


def test_redact_blacks_out_title_block_but_keeps_room_labels():
    original = _make_test_image()
    redacted = redact_pii(original)

    # Titelfeld-Region (enthielt Namen/Adresse/Kontakt) sollte jetzt fast
    # komplett dunkel (geschwaerzt) sein.
    title_block_dark = _count_dark_pixels(redacted, (490, 10, 890, 170))
    assert title_block_dark > 5000

    # Die Grundriss-Region (Raumlabels) sollte weiterhin ueberwiegend hell
    # sein (also NICHT geschwaerzt) - nur die duennen Buchstaben selbst sind dunkel.
    floorplan_dark = _count_dark_pixels(redacted, (10, 10, 400, 130))
    assert floorplan_dark < 2000


def test_redact_returns_valid_png_same_size():
    original = _make_test_image()
    redacted = redact_pii(original)

    before = Image.open(io.BytesIO(original))
    after = Image.open(io.BytesIO(redacted))
    assert before.size == after.size
