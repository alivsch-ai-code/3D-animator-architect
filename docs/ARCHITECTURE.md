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
| Claude-Vision-Parsing (Grundriss → strukturiertes JSON) | **Echt implementiert**, ruft die reale Anthropic-API |
| Normen-Kontext-Injektion | **Echt implementiert** (lädt STANDARDS.md) |
| Deterministischer 3D-Geometrie-Builder (GLB) | **Echt implementiert** (trimesh-Extrusion) |
| 3D-Tour im Browser (begehbar) | **Echt implementiert** (react-three-fiber + PointerLockControls) |
| Fotorealistisches Rendering | **Schnittstelle + einfacher Preview-Fallback implementiert.** Produktionsreifes Fotorealismus-Backend (SDXL/ControlNet oder Blender headless) muss noch angebunden werden — erfordert GPU-Infrastruktur, die in dieser Umgebung nicht verfügbar ist. Siehe `backend/app/pipeline/render.py` für den Erweiterungspunkt |
| IFC-Export | Nicht implementiert, Schema ist aber IFC-kompatibel angelegt (v2) |

## Nächste Schritte (Roadmap)

1. Render-Backend anbinden (Replicate/Stability-API für ControlNet, oder Blender-Worker).
2. Spezialisiertes Segmentierungsmodell (CubiCasa5K-trainiert, z.B. RoomFormer) als zweite
   Parsing-Quelle neben Claude Vision, zur Kreuzvalidierung der Wandkoordinaten.
3. Türöffnungen als echte Boolean-Cutouts statt Wandsegment-Lücken (bessere Fensterrahmen-Optik).
4. Mehrgeschossige Gebäude (Treppen, Geschossstapelung — IFC `IfcBuildingStorey`).
5. Echter IFC-Export für Übergabe an Architekturbüros/BIM-Tools.
