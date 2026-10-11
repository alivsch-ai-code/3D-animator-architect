# Wettbewerbsanalyse: Grundriss → Fotorealismus + 3D-Tour

> Recherchestand: 2026-10-11. Quellen sind inline verlinkt.

## A. Kommerzielle Wettbewerber

| Produkt | Input | Geometrische Treue zum Quellgrundriss | Vermutete Technik | Zielgruppe |
|---|---|---|---|---|
| [CubiCasa](https://www.cubi.casa/) | Handy-Scan (LiDAR/Video) der realen Immobilie | Hoch — aber weil der Grundriss ERST aus dem Scan erzeugt wird, nicht aus einer vorhandenen Zeichnung | Mobile SLAM/Photogrammetrie + proprietäre CV | Makler, Gutachter |
| [Giraffe360](https://www.giraffe360.com/) | 360°-Kamera + LiDAR der realen Immobilie | Hoch, da reale Räume gemessen werden (kein 2D-Input) | LiDAR + "RapidAI" | Agenturen mit hohem Foto-Durchsatz |
| [Matterport](https://matterport.com) | 3D-Kamera/LiDAR-Scan | ~1% Messgenauigkeit laut Best-Practice-Doku; bekannte Probleme bei mehrstöckiger Verknüpfung & Glas/Spiegel | Punktwolken-SLAM, proprietäres Meshing | Immobilien, Hospitality, Baudokumentation |
| [RoomSketcher](https://www.roomsketcher.com) | Manuelles Nachzeichnen im Editor | Grundriss wird manuell nachgebaut → Treue hängt vom Menschen ab, nicht von KI | Manueller CAD-ähnlicher Editor + eigene Render-Engine | Makler, Homestager |
| [Getfloorplan](https://getfloorplan.com/) | Upload DWG/JPG/PNG | Marketing vage zu geometrischer Garantie | Vermutlich regelbasierte Extrusion + Render-Engine | Makler, Innenarchitekten |
| [Drafto](https://www.getdrafto.com/ai-floor-plan-to-render), [ArchiVinci](https://www.archivinci.com/), [ArchiGPT](https://www.archigpt.ai/ai-render-tools/floor-plan-to-render), [Rendair](https://rendair.ai/tools/floorplan-to-render) | 2D-Grundriss-Bild/PDF | **Das ist die zentrale Lücke.** Unabhängige Reviews: *"proportionally accurate but not dimensionally precise... geometry drift... claims of exact dimensional accuracy should be treated skeptically."* | Stable Diffusion/ControlNet (Canny/Depth) auf dem Grundrissbild | Architekten/Makler für schnelle Marketing-Visuals, nicht vermessungsgenau |
| [Maket.ai](https://www.maket.ai/) | Text/Sketch (Design-Generator, keine Rekonstruktion) | Vektor-Output, aber *generiert* neue Pläne nach Regeln statt einen bestehenden Plan exakt zu matchen | LLM → Vektor-Layout + Regel-Postprocessing | Architekten/Bauträger in früher Planungsphase |
| [Coohom](https://www.coohom.com/), [Planner5D](https://planner5d.com) | Manuelles Zeichnen im Editor, dann KI-Rendering | Geometrie exakt, weil der Mensch (oder ein Zeichner) den Plan manuell neu einträgt | Eigene Render-Engine | Innenarchitekten, Verbraucher, einige Makler |
| [REimagineHome](https://reimaginehome.ai), [Styldod](https://styldod.com) | Raumfoto (kein Grundriss) | Struktur bleibt erhalten, da von echtem Foto ausgehend — adressiert aber nicht das Grundriss-Problem | Diffusion-Inpainting mit Struktur-Masken | Virtual Staging |
| [Spacely AI](https://spacely.ai) | Sketch/Foto | Keine Garantie exakter Maße | Diffusion-basiert, SketchUp-Integration | Designer, Makler |
| RoomGPT, PadStyler, Collov AI, VisualizeAI | Nur Raumfotos | N/A — reines Foto-Staging, kein Grundriss-Input | Diffusion-Styling | Makler, Stager |
| ArkoAI | Volles 3D-Modell (SketchUp/Rhino/Revit) via Plugin | Hoch — weil Input bereits echte 3D-Geometrie ist | Cloud-Render + Diffusion-Postprocessing auf echter BIM-Geometrie | Architekten mit vorhandenem CAD/BIM-Modell |

## B. Open-Source-Bausteine

| Repo | Zweck | Lizenz |
|---|---|---|
| [CubiCasa/cubicasa5k](https://github.com/cubicasa/cubicasa5k) | 5.000-Bilder-Datensatz (Wände/Räume/Icons gelabelt), Standard-Benchmark | Dataset + Modell, Research |
| [zlzeng/DeepFloorplan](https://github.com/zlzeng/DeepFloorplan) | Multi-Task-CNN: Raumgrenzen + Raumtyp-Segmentierung | GPL-3.0 |
| [zcemycl/PyTorch-DeepFloorplan](https://github.com/zcemycl/PyTorch-DeepFloorplan) | PyTorch-Reimplementierung | MIT |
| [ywyue/RoomFormer](https://github.com/ywyue/roomformer) (CVPR 2023) | Transformer sagt Raumpolygone direkt als Vektoren voraus — starker Kandidat für exakte Geometrie-Extraktion | MIT |
| PolyRoom ([arXiv 2407.10439](https://arxiv.org/pdf/2407.10439)) | Verbessert RoomFormer für Grundriss-Vektorisierung | Research |
| [grebtsew/FloorplanToBlender3d](https://github.com/grebtsew/FloorplanToBlender3d) | Bild → Blender-3D-Räume (Wände aus erkannten Linien extrudiert) | OSS |
| [priyanshsoni096-blip/PlanTo3D](https://github.com/priyanshsoni096-blip/PlanTo3D) | End-to-End: CubiCasa5K-Segmentierung → OCR-Maßextraktion → trimesh/Open3D-Mesh → Three.js-Viewer → Blender+ControlNet-Fotorealismus. **Dem hier geplanten Ansatz am nächsten** | Lizenz prüfen |
| [3dlg-hcvc/plan2scene](https://github.com/3dlg-hcvc/plan2scene) | Grundriss + Fotos → texturiertes 3D-Mesh | Academic |
| [neu-vi/houseCrafter](https://github.com/neu-vi/houseCrafter) (ICCV 2025) | Grundriss → multi-view-konsistente RGB-D via Diffusion → 3D-Rekonstruktion. Aktuellster Forschungsansatz | Academic, Code seit Okt. 2025 |
| [princeton-vl/infinigen](https://github.com/princeton-vl/infinigen) | 100% prozedurale, KI-freie Generierung fotorealistischer Häuser in Blender | BSD-3-Clause |
| Panolens.js, Photo Sphere Viewer, Marzipano | WebGL/Three.js 360°-Tour-Viewer mit Hotspots | MIT |
| donmccurdy/three-gltf-viewer | glTF-Viewer in Three.js — Basis für Walkthrough-Viewer | MIT |

## C. Relevante Forschung (Kurzfassung)

- **DeepFloorplan** (Zeng et al., ICCV 2019) — Segmentierungs-Baseline.
- **RoomFormer / "Connecting the Dots"** (CVPR 2023) — Transformer sagt Raumpolygone direkt voraus, gut für exakte Geometrie.
- **House-GAN++, Graph2Plan, ArchiGAN, HouseDiffusion, GSDiff** — generieren *neue* Layouts nach Constraints, rekonstruieren aber keinen vorgegebenen Plan.
- **Plan2Scene** — Grundriss + Fotos → texturiertes Mesh; braucht reale Fotos als Texturquelle.
- **HouseCrafter** (ICCV 2025 Highlight) — architektonisch ähnlichster Ansatz, optimiert aber auf visuelle Konsistenz, nicht auf Maßtreue.
- **ControlNet** ([arXiv 2302.05543](https://arxiv.org/pdf/2302.05543)) — Konditionierungsmechanismus (Canny/Depth), auf dem praktisch jedes kommerzielle "Grundriss-zu-Render"-Tool basiert; hat kein Konzept exakter Raummaße → Geometrie-Drift ist strukturell bedingt, kein Tuning-Fehler.

## D. Synthese: Ist pixelgenaue geometrische Treue bereits gelöst?

**Nein — echte, aktuell offene Lücke, kein gelöstes Problem.** Zwei Lager, die beide das harte Problem umgehen:

1. **Scan-basierte Produkte** (CubiCasa, Giraffe360, Matterport) erreichen hohe Treue nur, weil Grundriss UND 3D-Modell aus demselben realen Scan stammen — sie lösen nicht "vorhandener 2D-Plan als einzige Quelle".
2. **2D-Plan-Input-Tools** (ArchiGPT, Drafto, Rendair, ArchiVinci) nutzen ControlNet/Diffusion-img2img auf dem Plan als Kanten-/Tiefenkarte — Reviews bestätigen explizit "geometry drift", Diffusionsmodelle approximieren Stil unter weicher struktureller Bedingung, keine harte geometrische Gleichheit zu Wand-/Tür-/Fensterkoordinaten.

**Implikation für unsere Architektur:** Geometrie und Pixel müssen entkoppelt werden:
1. Quellplan → exaktes Vektormodell (Wände/Türen/Fenster/Raumpolygone mit echten Maßen).
2. Deterministische Extrusion zu texturiertem 3D-Mesh (prozedural, nicht gelernt).
3. Diffusion/ControlNet nur für Material/Licht/Möblierung auf fixierter, bereits korrekter Geometrie — nie für Wand-/Tür-/Fensterpositionen.

Das ist exakt der Ansatz dieses Projekts. Positionierung **"Wir erfinden Ihre Wände nicht"** ist ein echtes, aktuell unbesetztes Differenzierungsmerkmal gegenüber allen geprüften Wettbewerbern.
