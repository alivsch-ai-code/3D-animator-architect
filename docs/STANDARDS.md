# Bau- und Zeichnungsstandards für die Grundriss-Pipeline

> Recherchestand: 2026-10-11. Diese Datei wird vom Backend als Kontext für die
> Claude-Vision-Parsing-Pipeline geladen (`backend/app/core/standards_context.py`).

## 1. Deutsche/DACH-Normen

| Norm | Regelt | Relevanz für die Pipeline | Einstufung |
|---|---|---|---|
| **DIN 277:2021-08** | Grundflächen (BGF/NRF/NUF) und Rauminhalte im Hochbau | Berechnung der m²-Angaben aus Wand-/Raumpolygonen. Achtung: Wohnfläche nach **WoFlV** folgt anderen Regeln (Deckenhöhe, Balkon-Abschläge) — separat berechnen | **Hard rule** für Flächenangaben |
| **DIN 1356-1** (abgelöst, jetzt in ISO 7519/ISO 128-2) | Ehem. Zeichnungskonventionen (Linienarten, Schraffuren, Symbole) | Hilft bei Interpretation älterer deutscher Pläne | Background |
| **DIN 18015** (-1/-2, 2021) | Elektroinstallation: Mindestanzahl Steckdosen/Schalter je Raumtyp | Nur relevant, falls später Lichtschalter/Steckdosen automatisch platziert werden | Background (v2) |
| **DIN 18040** (-1/-2) | Barrierefreies Bauen: Türbreiten ≥80cm (≥90cm barrierefrei), Bewegungsflächen 150×150cm | Plausibilitätscheck: Türbreite weit unter Norm → wahrscheinlich Parsing-/Maßstabsfehler | **Soft validation rule** |
| **HOAI** | Leistungsphasen 1–9 der Architektenleistung | Hilft einzuschätzen, wie präzise/schematisch ein Plan vermutlich ist (LP3 vs. LP5) | Background |
| **GEG** (ex-EnEV) | Energetische Kennwerte | Keine Geometrie-Relevanz für v1 | Out of scope v1 |

## 2. Internationale/ISO-Normen

| Norm | Regelt | Relevanz | Einstufung |
|---|---|---|---|
| **ISO 128-2** | Linienarten/-stärken (durchgezogen dick = Wandkante, gestrichelt = verdeckt, dünn = Maßlinie) | Direkt nutzbar zur Klassifikation von Strichen beim Parsing | **Hard parsing rule** |
| **ISO 7519** (2025, löst DIN 1356-1 ab) | Grundriss-Zeichnungskonventionen, Maßstäbe, Plantypen | Aktuelle internationale Referenz für Maßstabsangaben | **Hard reference** |
| **ISO 16739-1:2024 (IFC)** | Industry Foundation Classes — offenes BIM-Datenschema | **Zielschema** für die geparste Geometrie: IfcWall (Materiallagen = Wandstärke), IfcDoor/IfcWindow (mit IfcOpeningElement), IfcSpace (Raumpolygon + Fläche), IfcBuildingStorey | **Hard target schema** |
| **ISO 29481** | BIM Information Delivery Manual (Prozess, nicht Geometrie) | Konzeptionell: was muss je Pipeline-Stufe extrahiert werden | Background |
| **RICS IPMS 2 (Residential)** | Internationales Pendant zu DIN 277/WoFlV | Flächenregeln für nicht-deutsche Märkte | **Hard rule** (international) |

## 3. Zeichenkonventionen ohne formale Norm (praxisrelevant für den Parser)

- **Maßstäbe**: 1:50 (Wohnungen, Möbeldetail), 1:100 (Gesamtgebäude), 1:20 (Details). Höchste Priorität: wenn ein Maßstab/eine Maßkette im Plan steht, Pixelmessung dagegen kalibrieren statt umgekehrt.
- **Wandstärken** (Plausibilitätsbereich DACH): Innenwand nicht tragend ~10–15cm, Innenwand tragend ~15–30cm, Außenwand ~20–37,5cm (Mauerwerk + Dämmung).
- **Tür-/Fenstersymbole**: Tür = Linie (Blatt) + Viertelkreisbogen (Schwenkrichtung); Doppeltür = zwei Bögen; Schiebetür = parallele versetzte Linien; Fenster = 2–3 parallele Linien in der Wandöffnung ohne Bogen.
- **Maßketten/Raumbeschriftung**: Maßketten mit Hilfslinien an Außenkanten; Raumlabel meist Name + Nettofläche (m²) zentriert im Raumpolygon — zuverlässigste Quelle für Maßstabskalibrierung, hat Vorrang vor Pixelschätzung.

## 4. Leichtgewichtige Zwischenformate

- **CubiCasa5K-Annotationsformat**: SVG/JSON pro Element (Polygon/Polyline), ~80 Klassen. Guter Ausgangspunkt für unser internes Zwischenformat (`FloorPlanGeometry`, siehe `backend/app/models/schemas.py`), bevor es optional nach IFC gehoben wird.
- Kein einzelner leichter JSON-Standard existiert; übliches Muster: Polygon/Polyline + Klassenlabel + Flächenberechnung nach DIN 277/IPMS, optional Export nach IFC für BIM-Interop.

## 5. Priorisierung für den LLM-Kontext (beim Grundriss-Parsing geladen)

1. IFC-Kernentitäten (IfcWall, IfcDoor, IfcWindow, IfcOpeningElement, IfcSpace, IfcBuildingStorey) — Zielschema, direkt in den Prompt
2. ISO 128-2 Linienarten — für Strich-Klassifikation
3. ISO 7519 Maßstab-/Plankonventionen
4. DIN 277 Flächenberechnung (+ WoFlV für "Wohnfläche")
5. RICS IPMS 2 (international)
6. Praxis-Spickzettel: Maßstäbe, Wandstärken-Bänder, Tür-/Fenstersymbole (siehe Abschnitt 3 — als kompakte Tabelle in den Prompt)

**Warum IFC das richtige Zielmodell ist**: IFC hat bereits native Entitäten für jedes Grundriss-Element — Wände mit echter Stärke über Materiallagen, Öffnungen für Türen/Fenster, Räume mit Polygon-Geometrie und Flächenregeln analog zu DIN 277/IPMS, Geschossstapelung für mehrstöckige Gebäude. Als universelles BIM-Austauschformat (IfcOpenShell, Revit, ArchiCAD, glTF/USD-Konverter für Game-Engines) vermeidet IFC als Pipeline-Ausgabeformat individuelle Exporter pro Zielwerkzeug.

---

*Quellen: baunormenlexikon.de (DIN 277, DIN 1356-1/ISO 7519), pflege.de/enableme.de (DIN 18040-2), myelectricplan.com (DIN 18015-2), hoai.de (HOAI-Phasen), buildingsmart.org (ISO 16739/IFC, ISO 29481), rics.org/ipmsc.org (IPMS Residential), arxiv.org/abs/1904.01920 (CubiCasa5K), blueprintprimer.com/cedreo.com/coohom.com (Zeichenkonventionen).*
