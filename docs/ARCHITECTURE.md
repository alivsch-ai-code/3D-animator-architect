# Architektur

## Leitprinzip

> **Geometrie und Pixel werden entkoppelt.** Die Wettbewerbsanalyse ([COMPETITORS.md](COMPETITORS.md))
> zeigt: Jedes Produkt, das ein generatives Modell direkt auf den Grundriss-Pixeln arbeiten lässt
> (ControlNet/img2img), produziert "Geometry Drift" — Wände, die nicht ganz parallel sind, Räume,
> deren Proportionen zwischen Durchläufen wandern. Für einen Makler, der eine Immobilie verkauft,
> ist eine optisch hübsche aber maßlich falsche Darstellung ein Haftungsrisiko (Falschdarstellung
> der Immobilie), kein Feature.
>
> Deshalb: **Schritt 1 parst exakt. Schritt 2 baut deterministisch. Schritt 3 veredelt nur Material/Licht,
> nie Geometrie.**

## Pipeline

```
2D-Grundriss (Bild/PDF)
        │
        ▼
┌───────────────────────┐
│ 1. Parser              │  Claude Opus 5 (Vision) + Normen-Kontext (STANDARDS.md)
│    backend/pipeline/   │  → FloorPlanGeometry (Wände, Türen, Fenster, Räume, Maßstab)
│    parser.py           │  Compliance-Flags (DIN 18040 etc.) statt stillem Halluzinieren
└───────────┬────────────┘
            ▼
┌───────────────────────┐
│ 2. Geometrie-Builder    │  Deterministisch, NICHT generativ
│    backend/pipeline/   │  Extrudiert Wände/Öffnungen aus den exakten Koordinaten
│    geometry.py         │  → GLB-3D-Modell (Grundlage für Tour UND Render)
└───────────┬────────────┘
            ▼
      ┌─────┴─────┐
      ▼           ▼
┌───────────┐ ┌─────────────────┐
│ 3a. Render │ │ 3b. 3D-Tour      │
│ Material/  │ │ Three.js/        │
│ Licht-     │ │ react-three-fiber│
│ Pass auf   │ │ läuft direkt auf │
│ fixierter  │ │ demselben GLB —  │
│ Geometrie  │ │ kein zweites,    │
│ (pluggable)│ │ abweichendes     │
└───────────┘ │ Modell           │
              └─────────────────┘
```

Der entscheidende Architekturpunkt in 3a/3b: **Render und Tour nutzen dasselbe GLB-Mesh.**
Es gibt keine zweite, unabhängig generierte 3D-Repräsentation, die vom Foto-Rendering abweichen
könnte — das schließt die in der Konkurrenzanalyse beschriebene Inkonsistenz zwischen
Marketing-Bild und tatsächlicher Immobilie strukturell aus.

## Warum kein Ende-zu-Ende-Diffusionsmodell?

Siehe [COMPETITORS.md](COMPETITORS.md) Abschnitt D: Kein geprüfter Wettbewerber garantiert
Maßtreue, weil Diffusion/ControlNet Geometrie nur als weiche Bedingung (Kantenbild) kennt, nicht
als harte Zahl. Unser Ansatz behandelt Geometrie als Daten (Zahlen, IFC-ähnliches Schema), nicht
als Pixel-Muster.

## Zielschema der geparsten Geometrie: IFC-orientiert

Siehe [STANDARDS.md](STANDARDS.md) Abschnitt 5. `backend/app/models/schemas.py` bildet ein
leichtgewichtiges JSON ab, das sich direkt auf IFC-Kernentitäten abbilden lässt
(`IfcWall`→`Wall`, `IfcDoor`/`IfcWindow`→`Opening`, `IfcSpace`→`Room`), damit ein echter
IFC-Export (z.B. via `IfcOpenShell`) später ohne Schema-Bruch möglich ist.

## Backend (Python/FastAPI)

```
backend/app/
├── main.py                    FastAPI-Einstiegspunkt
├── core/
│   ├── config.py              Settings (API-Keys, Pfade) via pydantic-settings
│   └── standards_context.py   Lädt docs/STANDARDS.md als LLM-Promptkontext
├── models/
│   └── schemas.py             Wall, Opening, Room, FloorPlanGeometry, Project
├── api/
│   ├── projects.py            CRUD für Projekte
│   ├── floorplans.py          Upload + Parse-Trigger
│   └── tour.py                GLB-Auslieferung + Tour-Metadaten
├── pipeline/
│   ├── parser.py              Claude-Vision-Call → FloorPlanGeometry
│   ├── geometry.py            FloorPlanGeometry → GLB (trimesh, deterministisch)
│   └── render.py              Pluggable Fotorealismus-Interface (+ einfacher Preview-Fallback)
└── storage/                   Lokale Datei-Ablage (Uploads, generierte Modelle)
```

## Frontend (Next.js/TypeScript)

```
frontend/
├── app/
│   ├── page.tsx                      Landing + Upload + Projektliste
│   └── projects/[id]/page.tsx        Grundriss + geparste Daten (editierbar) + 3D-Tour + Render
└── components/
    ├── UploadForm.tsx
    ├── GeometryEditor.tsx            Korrektur der geparsten Wände/Räume vor 3D-Erzeugung
    └── TourViewer.tsx                react-three-fiber: GLB laden, Walk-Controls, Raum-Teleport
```

## Ehrlicher Stand des MVP (was echt funktioniert vs. was Schnittstelle ist)

| Komponente | Status |
|---|---|
| Grundriss-Vision-Parsing (→ strukturiertes JSON) | **Echt implementiert und live getestet** (Claude Opus 4.6 über Replicate, siehe LLM-DECISION.md) |
| Normen-Kontext-Injektion | **Echt implementiert** (lädt STANDARDS.md) |
| Deterministischer 3D-Geometrie-Builder (GLB) | **Echt implementiert**, inkl. korrekter Y-up-Achskonvertierung für glTF/three.js (siehe unten, Live-Testergebnis 2026-10-11: ohne diese Konvertierung stand das Modell "auf der Kante") |
| 3D-Tour im Browser (begehbar) | **Echt implementiert**: react-three-fiber + PointerLockControls (WASD+Maus), Raycasting-Kollisionserkennung gegen Wände, automatischer Spawn im Hauptwohnraum, Raum-Teleport-Buttons. **Hinweis**: Kollisions-/Spawn-Logik ist durch Geometrie-Tests und Backend-seitige Screenshot-Verifikation abgesichert, aber noch nicht in einem echten Browser interaktiv durchgeklickt (kein Browser in der Entwicklungsumgebung verfügbar) |
| Fotorealistisches Rendering (Innenraumansicht) | **Echt implementiert und live getestet** (Replicate FLUX.1 Depth, siehe LLM-DECISION.md). Kamera steht automatisch im Hauptwohnraum (`geometry.py::interior_camera_transform`), nicht mehr in einer Außenansicht des Gesamtgebäudes (Live-Testergebnis 2026-10-11: vorher wurde die Gebäude-Außenform von FLUX als Möbelstück interpretiert) |
| IFC-Export | Nicht implementiert, Schema ist aber IFC-kompatibel angelegt (v2) |

### Live-Testergebnis: Y-up/Z-up-Achsbug + Außenansicht-Kamera (2026-10-11)

Ein Live-Test über die öffentliche Deployment-URL (echtes Smartphone, echter
Browser) deckte zwei Bugs auf, die beide die Kernversprechen des Produkts
direkt betrafen:

1. **3D-Tour zeigte ein hochkant stehendes "Regal" statt eines Hauses.**
   Ursache: `build_scene()` ist intern Z-up (Höhe = Z-Achse, Grundriss in der
   XY-Ebene) — glTF/GLB verlangt laut Spezifikation aber Y-up. `trimesh`
   konvertiert das beim Export nicht automatisch. Fix: `export_glb()`
   rotiert die Szene vor dem Export um -90° um die X-Achse
   (`geometry.py::_Z_UP_TO_Y_UP`). Verifiziert durch Bounds-Vergleich vor/nach
   Export (Höhe lag danach korrekt auf der Y-Achse).
2. **Fotorealistisches Rendering sah aus wie ein Schrank, nicht wie ein
   Zimmer.** Ursache: Die Kamera für Depth-Map/Rendering nutzte eine
   generische Außen-/Vogelperspektive auf das gesamte Gebäudevolumen — FLUX
   interpretierte die kompakte Blockform als Möbelstück. Fix: neue
   `geometry.py::interior_camera_transform()` platziert die Kamera auf
   Augenhöhe (1,7m) nahe einer Raumecke, Blickrichtung zum Raumzentrum;
   `geometry.py::pick_main_room()` wählt dafür automatisch den größten
   "echten" Wohnraum (Wohnzimmer/Küche/Schlafzimmer/Bad, nicht Flur/Balkon/
   offene Höfe). Live mit Replicate FLUX Depth verifiziert: Ergebnis zeigt
   jetzt erkennbar ein Rauminneres mit Fenster, Tür, Bodenperspektive.

Als Konsequenz aus Bug 1 wurde auch der Frontend-Tour-Viewer überarbeitet
(`frontend/components/TourViewer.tsx`): Der begehbare Modus spawnt jetzt
automatisch im selben "Hauptraum" (gleiche Auswahllogik wie serverseitig),
statt an einer festen Außenposition zu starten, und besitzt eine
Raycasting-Kollisionserkennung gegen Wände sowie Raum-Teleport-Buttons für
einen geführten Rundgang.

## Live-Testergebnis: Modellwahl entscheidet stark über Geometrie-Qualität

Live-Tests mit echten, gemeinfreien Grundrissen
(`backend/tests/fixtures/floorplans/FINDINGS.md`,
`backend/tests/fixtures/floorplans/model_comparison/`) zeigen: Ein kleines
Vision-Chat-Modell (`lucataco/qwen3-vl-8b-instruct`, 8B) liest Textinhalte
(Raumlabels, Flächenangaben) zuverlässig, liefert bei maßlosen oder
komplexen Plänen aber **keine echte pixelgenaue Geometrie** — identische
Platzhalter-Boxen für sichtbar unterschiedlich große Räume. Ein größeres
offenes Modell (InternVL3.5-30B) war dabei nicht nur weiterhin schlecht
(räumlich inkohärent), sondern auch unverhältnismäßig teuer/langsam
($0.47, ~8 Minuten pro Lauf) — "größer" ist also nicht automatisch
"besser genug". Ein starkes proprietäres Modell (**Claude Opus 4.6**,
praktischerweise direkt über Replicate erreichbar ohne separaten
Anthropic-Key) lieferte dagegen im selben Test klar unterschiedliche,
plausible Raumgrößen bei vergleichbarer Laufzeit (~52s) — siehe
Screenshots im Vergleichsordner. **Konsequenz**: Modellwahl ist der
wirksamste Hebel, bevor eine aufwendigere Architekturänderung (dediziertes
Segmentierungsmodell, siehe Punkt 2 der Roadmap) nötig wird; Letzteres
bleibt als Option für noch höhere Zuverlässigkeit bei komplexen Plänen
relevant, ist aber nicht mehr die einzige Abhilfe.

## Live-Testergebnis: Deterministische Raumpolygon-Ableitung (2026-10-11, experimentell)

Ein Live-Bug zeigte: Der Parser generiert Wand- und Raumpolygon-Koordinaten
weitgehend UNABHAENGIG voneinander - in einem Testfall wurde ein Balkon
wiederholt (systematisch, nicht zufaellig) INNERHALB des Wohnzimmer-Polygons
platziert statt ausserhalb der Fassade. Recherche (u.a. Raster-to-Vector/Liu
et al. ICCV 2017, CubiCasa5K-eigene Ground-Truth-Pipeline, ein 2026er
Floorplan-VLM-Paper das exakt dasselbe Problem beschreibt) bestaetigte den
naheliegenden Loesungsansatz: Raumpolygone deterministisch als eingeschlossene
Flaechen des Wand-Liniennetzes ableiten (`shapely.ops.polygonize`-Verfahren,
implementiert in `backend/app/pipeline/topology.py::derive_room_polygons`)
statt den separat vom LLM gelieferten Polygon-Koordinaten zu vertrauen - das
garantiert *mathematisch* ueberlappungsfreie Raeume statt es nur zu erhoffen.

**Status: Implementiert und getestet (`tests/test_topology.py`), aber
bewusst NICHT in die Live-Pipeline eingebunden.** An echten, komplexen
Plaenen (kurze Innenwaende, uneinheitliche Koordinatenkonventionen - z.B.
startet eine Innenwand teils an der Wandmittellinie, teils an der Innenkante
einer angrenzenden Aussenwand) erzeugte die Ableitung trotz mehrerer
Sicherheitsnetze (Ueberlappungs-Check, Flaechen-Plausibilitaetspruefung,
Gesamtflaechen-Drift-Check) teils plausibel aussehende, aber FALSCHE
Raumgrenzen bei nicht direkt betroffenen Nachbarraeumen (ein Luecken-Leck an
einer Wandverbindung liess zwei Raum-Voids teilweise verschmelzen, die
Sicherheitsnetze griffen nicht zuverlaessig). Wird bewusst als bekannte
Baustelle dokumentiert statt eine unfertige Loesung live zu schalten, die
das Problem im Zweifel verschlimmbessert.

**Naechste Schritte fuer eine produktionsreife Version** (siehe
`topology.py`-Docstring fuer Details): Vertex-Snapping vor dem Puffern
(`shapely.snap()`) statt pauschaler Linienverlaengerung, getrennte Innen-/
Aussenkanten-Liniennetze statt Mittellinien-Puffer (vermeidet die
Flaechen-Ungenauigkeit durch Wandstaerke), und/oder den Parser explizit
anweisen, Wandkoordinaten konsistent auf dieselbe Referenz (Mittellinie) zu
beziehen, um die Notwendigkeit von Toleranz-Heuristiken ueberhaupt zu
reduzieren.

## Live-Qualitätsdiagnose: Grundriss-/Modell-Rework (2026-10-11)

Auf dem Live-Projekt `asdfa` (Projekt-ID `c213e9e4-0ca4-4024-bcce-93afc1c6593a`)
wurde der schlechte Rundgang direkt im Browser untersucht. Das Bild bestätigt,
dass es ein technischer Blockout und kein fotorealistischer Rundgang ist. Das
heruntergeladene GLB war nur 56,900 Bytes groß und enthielt 83 einfache Meshes.
Die aus dem Grundriss erkannten Möbel wurden jeweils als ein farbiger Quader
gebaut; der Viewer zentrierte die Orbit-Kamera zudem am Weltursprung statt am
Grundriss. Ein endloses Raster und ein zur Laufzeit extern geladenes HDRI
verschlechterten den Eindruck bzw. machten die Darstellung von einem externen
Host abhängig.

Die Untersuchung der vorhandenen Geometrie zeigte einen tieferen Fehler:

| Raum | Polygonfläche | Planfläche | Befund |
|---|---:|---:|---|
| Wohnzimmer | 18.41 m² | 27.79 m² | erhebliche Abweichung |
| Balkon | 6.94 m² | 5.20 m² | erhebliche Abweichung |
| Eltern | 20.78 m² | 16.76 m² | erhebliche Abweichung |
| Kind | 12.49 m² | 14.59 m² | Abweichung |
| Flur | ungültiges Polygon | 5.92 m² | ungültige Kontur |
| Küche | 6.40 m² | 7.92 m² | Abweichung |
| Bad | 9.65 m² | 5.61 m² | erhebliche Abweichung |

Die vorherige Polygonprüfung ließ Flächenabweichungen bis zu 70 % als
unauffällig durch. Sie wurde verschärft: symmetrische Abweichung bezogen auf
die größere Fläche, über 20 % als Warnung und über 40 % als Fehler, sowie
Prüfung ungültiger/zu kleiner Polygone, mehrfacher Raum-IDs und ungültiger
Wand-/Öffnungsmaße. Bei der Modellerzeugung werden diese Prüfhinweise erneut
aktualisiert und im Frontend als vorläufige, nicht maßhaltige Visualisierung
gekennzeichnet.

Die Pixel-CV-Extraktion wird als eigenständiger Geometriekandidat mit dem
Parser-Ergebnis verglichen; sie darf das Parser-Ergebnis nicht allein aufgrund
ihrer Existenz ersetzen. Die Wandnetz-Topologieableitung bleibt bis zu einem
nachgewiesenen Benchmark an echten komplexen Grundrissen deaktiviert. Bei
Flächenlabels, die Netto-/Wohnflächen darstellen, und Polygonkonturen gibt es
legitime Abweichungen durch Wandstärken und Messkonventionen. Ein Fehler-Flag
ist daher eine Prüfaufforderung, keine automatische Reparatur oder
baurechtliche Aussage.

Der Modell-Builder zerlegt erkannte Betten, Sofas, Küchenzeilen und
Sanitärobjekte jetzt in maßbegrenzte, typgerechte Mesh-Teile, statt pro Symbol
einen einzelnen Quader zu zeichnen. Das ist ein erkennbarer Fortschritt über
den Blockout, aber ausdrücklich **keine** echte Asset-Bibliothek und kein
fotorealistisches Möbelmodell. Für marketingfähige Qualität bleiben
lizenzierte GLB-Assets und PBR-Materialien erforderlich. Der Viewer richtet
die Übersicht an den Raumgrenzen aus, entfernt das störende Raster und
verwendet kein extern nachzuladendes HDRI.

Die Upload-Normalisierung korrigiert außerdem die EXIF-Orientierung von
Rasterbildern vor der Pixelanalyse. Eingaben mit schlechter Auflösung,
nicht lesbaren Labels oder nicht unterstützten Zeichnungsstilen bleiben eine
Grenze der bestehenden CV-Heuristik. Ohne erfolgreiches Fixture-/Live-
Benchmark wird die Rekonstruktion nicht als sicher korrigiert ausgewiesen.

## Nächste Schritte (Roadmap)

> Für den realistischeren Rundgang (echte Möbel-Assets, Licht/Postprocessing,
> KI-Video-Rundgang) siehe die ausführliche Recherche und Priorisierung in
> [REALISTIC-WALKTHROUGH.md](REALISTIC-WALKTHROUGH.md).

1. Pixel-CV-Rekonstruktion und Parser-Kandidat an annotierten Plänen
   benchmarken; Fehlerfälle als Fixtures festhalten, bevor CV breit zum
   Standard wird.
2. Lizenzierte, lokale Möbel-GLB-Bibliothek mit Maß-, Polycount- und
   Lizenzmanifest integrieren; Platzierung gegen Raumkonturen validieren.
3. Render-Backend anbinden (Replicate/Stability-API für ControlNet, oder Blender-Worker).
4. Spezialisiertes Segmentierungsmodell (CubiCasa5K-trainiert, z.B. RoomFormer) als
   primäre Geometrie-Quelle statt/zusätzlich zu reiner LLM-Koordinatenextraktion
   (siehe Live-Testergebnis oben).
5. Türöffnungen als echte Boolean-Cutouts statt Wandsegment-Lücken (bessere Fensterrahmen-Optik).
6. Mehrgeschossige Gebäude (Treppen, Geschossstapelung — IFC `IfcBuildingStorey`).
7. Echter IFC-Export für Übergabe an Architekturbüros/BIM-Tools.
