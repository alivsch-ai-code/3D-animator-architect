# Modellentscheidung: Welches LLM arbeitet im Hintergrund?

## Kernaussage zuerst

Ein LLM ist **nicht** die Bildgenerierungs-Engine dieses Produkts. Die Wettbewerbsanalyse
([COMPETITORS.md](COMPETITORS.md)) zeigt: Reine Diffusion/ControlNet-Ansätze ("Grundriss
als Bild rein, Rendering raus") erzeugen genau die "Geometry Drift", die wir vermeiden wollen.
Das LLM ist die **Verständnis- und Orchestrierungsschicht**:

1. **Grundriss-Interpretation (Vision)**: Raumlabels, Maßketten, Maßstab/Legende, Türanschlag,
   Treppenrichtung, Nordpfeil lesen.
2. **Strukturierte Extraktion**: Rohes JSON (Wände/Türen/Fenster/Räume) als erster Entwurf,
   kalibriert gegen die geladenen Normen ([STANDARDS.md](STANDARDS.md)).
3. **Plausibilitäts-/Compliance-Check**: z.B. Türbreite < DIN 18040 → Flag statt stilles Halluzinieren.
4. **Materialien/Stil/Möblierung**: Szenenbeschreibung für die Renderpipeline ("skandinavischer Stil,
   Eichenparkett, Nordfenster → diffuses Licht").
5. **Konversationsschicht**: Chat-Anpassungen durch den Makler ("wärmere Töne im Wohnzimmer").

Die **exakte 3D-Geometrie selbst entsteht deterministisch** (siehe [ARCHITECTURE.md](ARCHITECTURE.md)),
nicht generativ — das LLM liefert die Parameter dafür, nicht die Pixel.

## Empfehlung

| Rolle | Modell | Begründung |
|---|---|---|
| Grundriss-Vision-Parsing, Compliance-Reasoning, strukturierte JSON-Extraktion | **Claude Opus 5** (`claude-opus-5`) | Stärkste Vision+Reasoning-Kombination der Claude-5-Familie; verlässlichste strukturierte Ausgaben bei komplexen Mehrschritt-Constraints (Normen gleichzeitig einhalten) |
| Hochvolumige Nebenaufgaben: OCR-Nachbearbeitung, Chat-Turns, einfache Stil-Vorschläge | **Claude Sonnet 5** (`claude-sonnet-5`) | Deutlich günstiger/schneller, für die Masse an Routineaufrufen ausreichend; Opus wird gezielt nur für die harten Parsing-/Compliance-Calls gerufen |
| Fotorealistisches Rendering (Pixel) | **Kein LLM** — separate Diffusion/Render-Engine (siehe unten) | Bild-Pixel-Generierung ist kein LLM-Task |
| 3D-Tour-Darstellung | **Kein LLM** — Three.js/WebGL auf dem deterministisch erzeugten Mesh | Rendering/Navigation ist reine Grafik-Engine-Aufgabe |

## Warum nicht GPT-4V/Gemini als Alternative?

Technisch wären GPT-5/Gemini-3-Vision ebenfalls vision-fähig. Die Empfehlung für Claude Opus 5 beruht auf:
- Stärkste Performance bei strukturierter, constraint-reicher JSON-Ausgabe (viele gleichzeitig zu prüfende Normen) — kritisch, da falsche Struktur direkt zu falscher Geometrie führt.
- Einheitlicher Anbieter/API für Opus (Vision+Reasoning) und Sonnet (Volumen), reduziert Integrationsaufwand.
- Dies ist eine Empfehlung, kein Lock-in: Die `LLMClient`-Schnittstelle in `backend/app/pipeline/parser.py` ist bewusst austauschbar gehalten.

## Was die Bildgenerierung tatsächlich übernimmt (nicht Teil des LLM)

Für die fotorealistische Render-Stufe (Stufe nach der exakten 3D-Geometrie) wird eine
**pluggable Schnittstelle** (`backend/app/pipeline/render.py`) bereitgestellt, in die z.B.
eingebunden werden kann:
- SDXL/FLUX + ControlNet (Depth/Canny aus dem exakten 3D-Mesh) — Stil/Material/Licht auf
  bereits fixierter Geometrie, z.B. via Replicate/Stability API oder selbst gehostetes ComfyUI.
- Blender headless (Cycles/EEVEE) für klassisches, geometrisch exaktes Rendering — langsamer,
  aber kontrollierbarer, kein Risiko von Geometrie-Drift.

Im MVP ist ein einfacher, GPU-freier Vorschau-Renderer (trimesh-basiert) implementiert, der
die exakte Geometrie korrekt aber nicht fotorealistisch zeigt — die Schnittstelle ist bewusst
so geschnitten, dass einer der obigen Dienste später ohne Architekturänderung eingehängt werden kann.
