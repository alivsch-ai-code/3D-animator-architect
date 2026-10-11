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

## 4. Live-Diagnose und aktueller Rework-Stand (2026-10-11)

Der aktive Live-Fall wurde im Browser geprüft und der GLB separat vermessen.
Das Modell hatte 56.9 KB und 83 Meshes. Die Wohnung war als farbiger
Grundriss-Blockout mit flachen Farbflächen und Quader-Möbeln sichtbar; das war
nicht „realistisch genug“. Im ursprünglichen Viewer zielte die Orbit-Kamera
auf (0,0,0), obwohl die Raumpolygone über ungefähr 9.6 × 11.9 m verteilt
waren. Zusätzlich legten ein unendliches Raster und ein extern geladenes HDRI
technische Hilfsdarstellung über die Szene.

Der Viewer berechnet seinen Überblick nun aus den Raum-Polygonen, zielt auf
deren tatsächliche Mitte, entfernt das Raster und verwendet kein externes
HDRI. Für den Walkthrough werden erkannte Möbel als proportionierte,
typisierte Mesh-Gruppen (Bett, Sofa, Küche, Badobjekte) gebaut, nicht als
einzelne farbige Box. Eingabe-Bilder werden vor der Analyse EXIF-orientiert.
Die geometrische Prüfung vergleicht Plan- und Polygonflächen, erkennt
ungültige Raumkonturen sowie falsche Wand-/Öffnungsmaße und zeigt kritische
Fälle sichtbar als vorläufig.

Die aktuelle Verbesserung hebt das Ergebnis aus dem besonders schlechten
Blockout, macht es aber nicht fotorealistisch: Es gibt weiterhin keine
produktionsreifen Möbel-GLB-Assets und keine PBR-Texturen. Ebenso ist die
pixelbasierte CV-Extraktion nicht automatisch für jeden Plan geeignet.
Sie wird nur als eigener Kandidat gegen die Parsergeometrie bewertet; die
experimentelle Wandnetzableitung bleibt aus, bis sie auf annotierten echten
Plänen nachweislich besser ist.

**Qualitätsgrenze:** Der Live-Fall erfüllt den Benchmark unten noch nicht.
Die nachfolgenden Maßnahmen sind technische Verbesserungen und Regression-
Schutz, aber kein Beleg für vertriebsreife Fotorealistik. Vor Freigabe sind
Browser-Sichtprüfung und annotierte Referenzpläne weiterhin erforderlich.

## 5. Finaler Benchmark: „realistisch genug für Live-Walkthrough“

Nicht alles, was im Browser "gut aussieht", ist für ein Immobilien-Listing ausreichend. Der Produkt-Benchmark sollte an echten Nutzer-Lesezeichen orientiert sein, nicht nur an technischen Render-Features:

- Raumgefühl: Eine Person kann auf Anhieb einsehen, wo der Wohn-/Schlaf-/Essbereich liegt, ohne in einem Schachtelmodell zu navigieren.
- Blickrichtung: Der Visitor muss im Übergang zwischen Räumen nicht abrupt in die Wand, auf den Boden oder in einen Balkon schauen.
- Möbel-Silhouette: Sofas, Betten, Küchenelemente, Badmöbel und Tischbereiche sind als klar erkennbare reale Objekte lesbar.
- Licht/Material: Holz, Fliesen, Stoff und Wände unterscheiden sich deutlich im Ton und in der Reflexion; keine flachen, blauen oder "Blockout"-Farben mehr.
- Topologie: Räume sind nicht überlappt, richtig geschlossen und beim Wechsel zwischen Räumen orientierungsstabil.

### Metrik / Qualitätsgrenze

Ein Rundgang gilt als **„realistisch genug für Live-Walkthrough“**, wenn folgende Kriterien für die typische 2-4-Zimmer-Objektvorlage erfüllt sind:

1. Keine Topologie-Fehlermeldungen bei validem Grundriss: `find_room_overlaps()` und die Polygon-Prüfungen liefern keine Fehler mehr.
2. Die Startkamera landet immer innerhalb des Hauptraums, nicht im Zentrum der Gesamtfläche und nicht im Flur.
3. Sichtbare Möbel-Silhouetten sind in jedem relevanten Raum klar erkennbar, nicht nur einzelne Boxen.
4. Die Szene wirkt bei 10-20 Sekunden Rundgang nicht "leer" oder künstlich, sondern assoziiert mit einer echten Wohnung.
5. Die Kamera und die Bewegung fühlen sich in der Praxis wie Innenraum statt wie 3D-Blockout an.

Für den aktuellen Produkt-Stack ist dieser Benchmark **realistisch erreichbar**, ohne einen Full-Engine-Umstieg: Fertige 3D-Assets + bessere Licht-/Material-Palette + topologische Validierung reichen bereits für die nächste Qualitätsstufe.

## Empfohlene Reihenfolge

1. Parser/CV-Kandidaten anhand manuell annotierter Grundrisse validieren und die
   Schwellenwerte so abstimmen, dass Fehler nicht als maßhaltige Geometrie
   ausgegeben werden.
2. Möbel-/Material-Asset-Bibliothek aufbauen und Platzierung in echten
   Raumkonturen validieren (größter visueller Gewinn).
3. Licht/Postprocessing-Politur im Frontend, erst nach echten Asset-Modellen.
4. Video-Rundgang-Experiment (eigenständiges Deliverable).
5. Nur falls danach nötig: Lightmap-Baking für statische Elemente.
