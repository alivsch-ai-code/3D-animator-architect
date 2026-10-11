# Live-Testergebnisse: Parser-Provider an echten Grundrissen

> Getestet am 2026-10-11 gegen `PARSER_PROVIDER=replicate`
> (`lucataco/qwen3-vl-8b-instruct`), siehe gespeicherte Rohergebnisse
> (`*.replicate_result.json`) neben den jeweiligen Bildern.

## Zusammenfassung

Das günstige, offene Replicate-Modell (8B Parameter) ist für den **Kern der
Produktversprechung — geometrisch exakte Koordinaten-Extraktion — nicht
ausreichend**, sobald der Grundriss keine expliziten Maßangaben enthält. Es
liest Textinhalte (Raumlabels, Flächenangaben, Maßstabstext) zuverlässig,
aber die tatsächlichen Wand-/Raumkoordinaten sind bei komplexeren oder
maßlosen Plänen **nicht aus dem Bild gemessen**, sondern generische Platzhalter.

## Testfall 1: `synthetic_simple_apartment.pdf` (Kontrollfall, explizite Maße)

- ✅ Maßstab korrekt erkannt: `"1:100"`
- ✅ Flächenangaben aus Textlabels korrekt übernommen (20 m², 9 m²)
- ❌ Tatsächliche Raumpolygone sind **beide identisch klein** (2×2m bzw.
  2×1m) — die Bounding-Box stimmt weder mit den Textlabels noch mit der
  realen Zeichnung überein. Das Modell hat die Zahl aus dem Text gelesen,
  aber keine echte Geometrie daraus abgeleitet.

## Testfall 2: `davies_house_1951.png` (echtes Haus, keine Maßangaben)

- Erster Versuch (vor Prompt-Fix): **0 Wände, 0 Räume** — Modell hat bei
  fehlendem Maßstab komplett verweigert statt zu schätzen.
- Nach Prompt-Fix (explizite Anweisung, nie leer zurückzugeben und typische
  Raumgrößen zur Schätzung zu nutzen): 24 Wände, 8 Räume zurückgegeben —
  aber **jeder einzelne Raum hat exakt dieselbe 2×2m-Bounding-Box**,
  unabhängig von der sichtbar sehr unterschiedlichen Größe im Original
  (z.B. "Court" ist im Bild der mit Abstand größte Bereich, bekam aber
  dieselbe 2×2m-Box wie ein Schlafzimmer). Das Modell hat ein plausibles
  *Schema* ausgefüllt, aber keine echte visuelle Vermessung vorgenommen.

## Testfall 3: `hampton_court_apt_1911.png` (komplexes Mehrfamilienhaus)

- **0 Wände, 0 Räume**, obwohl `source_notes` behauptet, ein Maßstab sei
  geschätzt worden — Antwort intern widersprüchlich.
- Wahrscheinliche Ursache: Output-Token-Limit. Das Modell ist bei diesem
  Provider auf `max_new_tokens=4096` begrenzt (Modell-Hardcap, siehe
  `backend/app/pipeline/parser.py::ReplicateFloorPlanParser`); bei ~20
  Räumen reicht das nicht, um unser vollständiges, verschachteltes
  JSON-Schema (Koordinaten pro Wand + Öffnungen) auszugeben.

## Einordnung: kein reines Prompt-Problem, sondern eine bekannte VLM-Schwäche

Pixelgenaue Koordinaten-Extraktion ("Grounding") ist eine dokumentierte
Schwachstelle von Vision-Language-Modellen generell, nicht nur dieses
konkreten 8B-Modells — reine LLM-Vision-Modelle sind nicht primär auf
präzise räumliche Koordinatenausgabe trainiert. Das deckt sich mit der
Wettbewerbsrecherche (`docs/COMPETITORS.md`, Abschnitt D): Der akademische
Stand der Technik (RoomFormer, CubiCasa5K-trainierte Segmentierungsmodelle)
verwendet dedizierte CV-Segmentierungsmodelle für die Geometrie-Extraktion,
nicht ein generisches Vision-Chat-Modell.

## Empfehlung / nächste Schritte

1. **Kurzfristig**: Mit `PARSER_PROVIDER=claude` (Claude Opus 5) denselben
   Testlauf wiederholen, sobald ein Anthropic-Key verfügbar ist — starke
   Vision-Modelle sind bei Grounding-Aufgaben erfahrungsgemäß deutlich
   besser, aber auch das sollte an echten Daten verifiziert werden statt
   angenommen.
2. **Mittelfristig (siehe docs/ARCHITECTURE.md Roadmap)**: Ein spezialisiertes
   Segmentierungsmodell (RoomFormer oder ein CubiCasa5K-trainiertes Modell)
   für die reine Geometrie-Extraktion vorschalten; das LLM übernimmt dann nur
   noch Semantik (Raumtyp-Labels, Normprüfung, Stilbeschreibung) auf bereits
   korrekt vermessener Geometrie — das war bereits die ursprüngliche
   Architekturempfehlung aus der Wettbewerbsrecherche und wird durch diesen
   Test zusätzlich bestätigt.
3. Für sehr komplexe Pläne (viele Räume) ggf. das JSON-Schema kompakter
   gestalten oder den Plan in Abschnitte aufteilen, um Output-Token-Limits
   einzelner Provider nicht zu sprengen.
