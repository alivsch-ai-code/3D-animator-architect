# Realistischer Rundgang: Recherche & Umsetzungsplan

> Recherchestand: 2026-10-11. Drei parallele Recherchen zur Frage "wie macht
> man den 3D-Rundgang (begehbare Tour) realistisch/'Unity-like'" statt nur
> die bereits funktionierenden Einzelbild-Renderings (FLUX.1 Depth). Siehe
> auch [LLM-DECISION.md](LLM-DECISION.md) für die Fotorealismus-Pipeline und
> [ARCHITECTURE.md](ARCHITECTURE.md) für den Gesamtkontext.

## Kernaussage

**Kein Engine-Wechsel** (Unity/Unreal/Babylon/PlayCanvas) — der bestehende
Three.js/react-three-fiber-Stack bleibt richtig. Der "nicht realistisch"-
Eindruck kommt überwiegend von Möbel-/Material-Qualität, nicht von fehlender
globaler Beleuchtung. Zwei unabhängige, kombinierbare Ausbaustufen:

1. **Interaktiver Rundgang verbessern** (Möbel-Assets + Materialien + Licht/Postprocessing)
2. **Zusätzlich: KI-generierter Video-Rundgang** als neues, eigenständiges Deliverable

## 1. Warum kein Engine-Wechsel

| Engine | Befund | Verdikt |
|---|---|---|
| Unity WebGL | WebGPU-Backend seit 6.6 nicht-experimentell, aber aus; braucht eine zweite, parallele Szene-Erzeugungs-Pipeline (C#) zusätzlich zur Python-Pipeline; mehrere hundert MB WASM-Download pro Handy-Besuch | Zu hoher Aufwand für pro-Listing generierte Szenen |
| Unreal Pixel Streaming | Echtes Unreal-Niveau, aber cloud-gerendertes Video, **eine GPU-Instanz pro gleichzeitigem Betrachter** (~0,53–1 $/h T4/A10, mehr bei RT) | Nur bei hoher Marge/planbarem Traffic sinnvoll |
| PlayCanvas | Web-nativ, gute PBR-Pipeline, aber **keine Echtzeit-GI** | Kein klarer Vorteil ggü. Three.js |
| Babylon.js | Einzig proportionaler Tausch (WGSL-nativ seit 8.0, Clustered Lighting seit 9.0/2026) | Kein GI-Unlock, volle Migrationskosten ohne Feature-Gewinn |

glTF/GLB hat **keinen Lightmap-Slot** — Baking ist möglich (Blender/
Cycles auf zweiten UV-Kanal, Export als separates PNG, manuelle Zuweisung an
`material.lightMap` nach dem Laden), aber echte Zusatzarbeit (Tage, nicht
Checkbox). `drei`'s `<Environment>` + eigene HDRI + ein paar
`RectAreaLight`s ist das pragmatische 80/20 ohne Baking-Pipeline.

## 2. Empfohlene Ausbaustufen für den interaktiven Rundgang (Priorität)

1. **Box-Platzhaltermöbel durch echte CC0-GLB-Modelle ersetzen** — größter visueller Gewinn pro Aufwand, da Silhouette vor Beleuchtung "real" wirkt.
2. **Selbst gehostete Interieur-HDRI** (nicht `drei`'s CDN-Preset, der niedrig aufgelöst ist) + 2-4 `RectAreaLight`s an Fenstern/Leuchten + korrektes Tone-Mapping (ACESFilmic).
3. **`@react-three/postprocessing`**: SSAO (pmndrs-Effekt, nicht `SSAOPass`), dezentes Bloom mit hoher Schwelle, selektives SSR nur für Boden/Glas — auf Mobil-GPUs testen (Handy-first-Produkt).
4. **Erst danach, falls nötig**: Blender-`bpy`-Headless-Bake-Pipeline für statische Elemente (Boden/Wände) — für bewegliche Möbel überspringen.

### Lizenzsichere Asset-Quellen (geprüft, Stand Okt. 2026)

| Quelle | Lizenz | Inhalt | Hinweis |
|---|---|---|---|
| [Poly Haven](https://polyhaven.com/license) | **CC0**, kommerziell frei, keine Attribution | 85 Möbel-Modelle + 22 Geräte (Betten, Sofas, Sessel, Tische, Regale); Beispiel `Sofa_01` = 4.101 Tris (echtzeit-tauglich) | **Keine** Bad-Armaturen (Wanne/WC/Waschbecken) im Sortiment |
| [Kenney Furniture Kit](https://kenney.nl/assets/furniture-kit) | **CC0 1.0** | 140 Dateien, Low-Poly/stilisiert, deckt Küche (Theke/Herd/Kühlschrank/Spüle) **und Bad** (WC/Wanne/Waschbecken) ab | Einziger geprüfter Anbieter mit Bad-Armaturen out of the box |
| [Quaternius](https://quaternius.com) | ⚠️ **Nicht mehr CC0** seit 28.8.2026 — jetzt "Quaternius Asset License v1.0": kommerzielle Nutzung ok, **kein Weiterverkauf/Redistribution der Roh-Assets** | "Ultimate Furniture Pack" / "Ultimate House Interior Pack" | Lizenztext pro Download-Snapshot aufbewahren, da sich die Lizenz schon einmal geändert hat |
| [Poly Haven Textures](https://polyhaven.com/textures) / [ambientCG](https://docs.ambientcg.com/license) | **CC0**, kommerziell frei | PBR-Sets (Diffuse/Normal/Roughness/AO) für Holzboden, Fliesen, Putz/Wandfarbe, Stoff | 1K/2K/4K, kleine Dateigrößen bei 1K |
| Sketchfab | **Pro Uploader unterschiedlich** | Viel Auswahl | Nur CC0 oder Sketchfab "Standard License" sicher; CC-BY braucht Attribution (unpraktisch); CC-BY-NC/ND und "Editorial License" **ausschließen**. Zu inkonsistent für automatisierten Einsatz im großen Stil |
| [Khronos glTF-Sample-Assets](https://github.com/KhronosGroup/glTF-Sample-Assets) | Pro Modell unterschiedlich, teils reale Marken-IP (z.B. IKEA-Modell) | — | Nur zum Format-Testen, **nicht** als Asset-Quelle verwenden |

**Empfohlener Aufbau**: Einmalig eine lokale, versionierte Asset-Bibliothek
herunterladen (Poly Haven als Basis + Kenney zur Lücken-Füllung bei Küche/
Bad), mit Manifest (Pfad, Kategorie, Maße, Polycount, Lizenz+Quelle-URL) -
Raum-Typ → Möbel-Auswahl wird dann ein reiner lokaler Lookup ohne Laufzeit-
Lizenzrisiko. Platzierungslogik muss selbst gebaut werden (kein fertiges
Open-Source-"Raumpolygon+Typ→Möbelpositionen"-Tool gefunden) — Shapely
(Wandabstand-Puffer, Türfreiraum-Ausschlusszonen) + ein 2D-Rechteck-Packer
(z.B. [rectpack](https://github.com/findux/rectpack)) als Grundlage.

## 3. Zusätzliche Option: KI-generierter Video-Rundgang

Kein fertiges "Tiefenkarte rein, Video raus"-Modell existiert produktionsreif
(selbst akademische Ansätze wie [VideoFrom3D](https://arxiv.org/abs/2509.17985),
SIGGRAPH Asia 2025, sind sehr neu). Kommerzielle Tools wie TensorPix oder
Dreamina/CapCut Seedance generieren nur **prompt-geführt** ("Wände/Türen an
derselben Stelle lassen"), **nicht geometrisch exakt** — wir wären mit
unserem Tiefenkarten-Ansatz dem kommerziellen Feld voraus.

**Empfohlenes nächstes Experiment** (erweitert die bestehende FLUX.1-Depth-
Pipeline, kein neues Modell nötig):

1. Kamera-Pfad durch 2-3 Räume, **15-25 eng gestaffelte Tiefenkarten**
   (~0,3 m Translation / ~5-8° Rotation zwischen Frames — enger als bei
   Einzelbildern, da Interpolationsqualität bei großen Sprüngen stark abfällt).
2. Jeden Frame mit FLUX.1 Depth rendern, **fester Seed + fester Stil-Prompt**
   für alle Frames (wichtigster Hebel gegen Flackern — unterschiedliche Seeds
   lassen Holzmaserung/Fliesen zwischen Frames "schwimmen").
3. Aufeinanderfolgende Frame-Paare durch [FILM](https://replicate.com/zsxkib/film-frame-interpolation-for-large-motion)
   (Replicate, ~0,13 $/Lauf, ~108s auf L40S) interpolieren → 24-30fps.
4. Mit ffmpeg zum Video zusammenfügen.

**Kostenschätzung** für 20-30s-Clip, 2-3 Räume: ~20 FLUX-Stills (bestehende
Kosten) + ~19 FILM-Interpolationen × 0,13 $ ≈ **2,50-4 $ zusätzlich**,
10-20 Minuten Laufzeit (FILM-Calls parallelisierbar).

**Bekanntes Risiko**: Flackern zwischen Anker-Frames, da FLUX.1 Depth keine
zeitliche Konsistenz kennt (gleiche Tiefenkarte, aber unterschiedliches
Rausch-Sampling → unterschiedliche Feintextur). Fester Seed hilft, löst es
aber nicht vollständig. Nächster Testschritt bei sichtbarem Flackern:
img2img mit niedriger Denoise-Stärke (vorherigen Frame als Teil-Init neben
der neuen Tiefenkarte einspeisen) statt jeden Frame aus reinem Rauschen zu
generieren — reine Parameteränderung an der bestehenden Pipeline, kein neues
Modell.

**Alternative, technisch näher an "echtem" Video-ControlNet**: Wan2.1/2.2
VACE unterstützt Tiefenkarten-Konditionierung nativ, ist aber nicht als
fertiges Replicate-Modell verfügbar — müsste selbst als Cog-Container
paketiert werden (deutlich mehr Aufwand als Option oben).

## Empfohlene Reihenfolge

1. Möbel-/Material-Asset-Bibliothek aufbauen + Platzierungslogik (größter Nutzen für das bestehende, bereits genutzte Feature)
2. Licht/Postprocessing-Politur im Frontend
3. Video-Rundgang-Experiment (eigenständiges neues Deliverable, günstig zu testen)
4. Nur falls danach noch nötig: Lightmap-Baking für statische Elemente
