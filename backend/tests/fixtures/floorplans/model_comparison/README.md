# Modellvergleich: Grundriss-Parsing an echten Daten

> Getestet am 2026-10-11 am Testfall `davies_house_1951.png` (siehe
> `../FINDINGS.md` für den ursprünglichen Befund, der diesen Vergleich
> ausgelöst hat: das kleine Replicate-Standardmodell lieferte keine echte
> Geometrie). Jeder Screenshot ist ein Top-Down-Rendering der vom jeweiligen
> Modell gelieferten Geometrie nach deterministischer 3D-Erzeugung
> (`app/pipeline/geometry.py`) — zeigt also exakt das, was auch im Produkt
> als begehbares 3D-Modell ankäme.

## Ergebnis

| Modell | Walls/Rooms | Qualität | Zeit | Kosten | Verdikt |
|---|---|---|---|---|---|
| `lucataco/qwen3-vl-8b-instruct` (Replicate, 8B) | 24 / 8 | ❌ Alle Räume identisches 2×2m-Platzhalter-Raster, keine echte Geometrie | ~10-100s | sehr günstig | Ungeeignet für maßlose/komplexe Pläne |
| `lucataco/internvl3_5-30b` (Replicate, 30B) | 18 / 7 | ❌ Räume falsch benannt (3× "Bad" statt Schlafzimmer), räumlich inkohärent (schwebende, unzusammenhängende Boxen) | **~8 Minuten** | **$0.47/Lauf** | **Nicht mehr verwenden** — schlecht UND teuer/langsam |
| `google/gemini-3.1-pro` (Replicate) | - | ⚠️ Beim ersten Versuch Output-Token-Limit erreicht (JSON abgeschnitten); beim Retry Token-Budget komplett fürs interne "Thinking" verbraucht, keine valide JSON-Antwort | ~50-110s | günstig | Brauchbar, aber Thinking-Modus muss erst konfiguriert werden (nicht weiter verfolgt) |
| **`anthropic/claude-opus-4.6`** (Replicate) | 20 / 11 | ✅ **Deutlich unterschiedliche, plausible Raumgrößen** (Court korrekt als größter Bereich erkannt: 24.8m², Bad klein: 4.1m², etc.), erkennbare L-Form des Hauses | ~52s | günstig (API-Pricing, kein GPU-Zeit-Billing) | **Neuer Standard** (`REPLICATE_PARSER_MODEL`) |

## Screenshots (Top-Down, aus identischer Quelle generiert)

- `davies_house_1951/qwen3-vl-8b.png` — uniformes 3×3-Raster, keine Beziehung zur echten Form
- `davies_house_1951/internvl3.5-30b.png` — schwebende, unzusammenhängende Boxen
- `davies_house_1951/claude-opus-4.6.png` — erkennbare L-Form, plausible Raumproportionen

Original-Grundriss zum Vergleich: `../davies_house_1951.png`

## Konsequenz

`backend/app/core/config.py`: `replicate_parser_model` Standard geändert von
`lucataco/qwen3-vl-8b-instruct` auf `anthropic/claude-opus-4.6`.
`backend/app/pipeline/parser.py::_build_replicate_input()` baut das
modellspezifische Input-Schema (Feldnamen unterscheiden sich je Anbieter auf
Replicate). Damit lässt sich die ursprüngliche Frage "braucht man zwingend
einen direkten Anthropic-Key?" mit **Nein** beantworten — Claude Opus 4.6 ist
direkt über Replicate nutzbar, ein einziger Replicate-Token reicht für
Parsing (Text) UND Rendering (Bild, `flux-depth-dev`).
