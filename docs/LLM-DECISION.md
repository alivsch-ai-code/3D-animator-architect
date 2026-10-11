# Modellentscheidung: Welches LLM arbeitet im Hintergrund?

> **Update 2026-10-11 nach Live-Vergleichstest**: Ursprünglich war die Empfehlung,
> Claude Opus 5 direkt über einen eigenen Anthropic-Key anzubinden. Ein
> Live-Vergleich mehrerer auf Replicate gehosteter Modelle
> (`backend/tests/fixtures/floorplans/model_comparison/`) zeigt: **Replicate
> hostet Claude (und Gemini) selbst als Endpunkte** — ein einziger
> Replicate-Token reicht damit für Parsing UND Rendering, kein separater
> Anthropic-/Google-Key nötig. Empfohlener Standard ist jetzt
> `anthropic/claude-opus-4.6` über `PARSER_PROVIDER=replicate`. Details siehe
> "Implementierte Provider-Alternativen" unten.

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

## Implementierte Provider-Alternativen (austauschbar über `.env`)

Auf expliziten Wunsch sind zwei weitere Backends real implementiert, nicht nur dokumentiert
(`backend/app/pipeline/parser.py`, Auswahl über `PARSER_PROVIDER`):

| Provider | `PARSER_PROVIDER` | Modell | Status | Einschätzung |
|---|---|---|---|---|
| **Replicate mit Claude Opus 4.6 (Standard/Empfehlung)** | `replicate` | `anthropic/claude-opus-4.6` (per `REPLICATE_PARSER_MODEL`) | ✅ **Live getestet (2026-10-11)**, siehe `backend/tests/fixtures/floorplans/model_comparison/README.md` | Im direkten Vergleich am echten, maßlosen Grundriss klar das beste Ergebnis: deutlich unterschiedliche, plausible Raumgrößen statt Platzhalter-Raster, erkennbare Gebäudeform. ~52s Laufzeit, API-Pricing (kein teures GPU-Zeit-Billing). **Läuft über den ohnehin vorhandenen Replicate-Token — kein separater Anthropic-Key nötig** |
| Claude direkt über Anthropic-API | `claude` | `claude-opus-5` | Implementiert, als Alternative falls bereits ein eigener Anthropic-Key/eigenes Kontingent vorhanden ist | Technisch gleichwertig oder potenziell noch aktueller (Claude-5-Familie) als der Replicate-Endpunkt (`claude-opus-4.6`), aber ohne Mehrwert gegenüber der Replicate-Variante, solange kein eigener Anthropic-Vertrag/Kontingent vorliegt |
| Google Gemini (direkt oder via Replicate) | `gemini` / `replicate` mit `google/gemini-3.1-pro` | `gemini-3-pro` bzw. `gemini-3.1-pro` | Getestet, aber **nicht empfohlen**: Im Test wurde entweder das Output-Token-Limit durch die finale JSON-Antwort gesprengt, oder (bei höherem Limit) das gesamte Budget vom internen "Thinking"-Modus verbraucht, sodass keine valide JSON-Antwort mehr ankam. Lösbar (Thinking-Parameter tunen), aber nicht weiter verfolgt, da Claude Opus 4.6 bereits überzeugt | 
| ~~`lucataco/qwen3-vl-8b-instruct`~~ | `replicate` (alte Voreinstellung) | 8B offenes Modell | ❌ **Nicht mehr Standard** | Ursprünglicher Test-Default; liefert bei maßlosen/komplexen Plänen keine echte Geometrie (identische Platzhalter-Raumgrößen). Für sehr einfache, gut bemaßte Pläne als Kostenoption weiter nutzbar, aber nicht die Empfehlung |
| ~~`lucataco/internvl3_5-30b`~~ | - | 30B offenes Modell | ❌ **Nicht verwenden** | Schlechtere, räumlich inkohärente Ausgabe UND mit $0.47/~8 Minuten pro Lauf unverhältnismäßig teuer und langsam für ein mittelmäßiges Ergebnis |

Für die **Bild-/Fotorealismus-Stufe** (`backend/app/pipeline/render.py`, Auswahl über `RENDER_PROVIDER`):

| Provider | `RENDER_PROVIDER` | Modell | Status | Einschätzung |
|---|---|---|---|---|
| **Preview (Standard, kein Key nötig)** | `preview` | trimesh-Vorschau | Implementiert | GPU-frei, korrekt aber nicht fotorealistisch — ehrlicher Platzhalter |
| **Replicate** | `replicate` | `black-forest-labs/flux-depth-dev` (per `REPLICATE_IMAGE_MODEL` konfigurierbar) | ✅ **Live getestet (2026-10-11)** | **Empfehlung für produktives Fotorealismus-Rendering.** FLUX.1 Depth [dev] nimmt eine Depth-Map + Stil-Prompt; die Depth-Map wird direkt aus dem exakten GLB gerendert (nicht aus einem zweiten, unabhängigen Modell) — damit bleibt die Geometrie-Garantie aus `ARCHITECTURE.md` auch in der Pixel-Stufe erhalten. Testlauf ergab ein überzeugend fotorealistisches, geometrisch konsistentes Bild. Alternative: `black-forest-labs/flux-canny-dev` für Kantenkonditionierung statt Tiefe |

Benötigte Env-Variablen stehen gesammelt in `backend/.env.example`. Beide Replicate-Modellreferenzen
werden zur Laufzeit automatisch auf eine versions-gepinnte Referenz (`owner/name:version`) aufgelöst
(`backend/app/pipeline/parser.py::_resolve_version_ref`), da manche Community-Modelle den reinen
`owner/name`-Shortcut nicht akzeptieren (im Testlauf bei `qwen3-vl-8b-instruct` beobachtet, 404).

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
