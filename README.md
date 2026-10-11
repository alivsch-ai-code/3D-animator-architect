# 3D Animator Architect

2D-Grundriss (Haus/Wohnung) → exaktes 3D-Modell → fotorealistisches Rendering →
begehbare 3D-Tour im Browser. Gebaut für Makler, die Immobilien aus einer
Bauzeichnung heraus überzeugend und **maßtreu** vermarkten wollen.

## Warum das anders ist als bestehende Tools

Bestehende "Grundriss-zu-Render"-Produkte (siehe [docs/COMPETITORS.md](docs/COMPETITORS.md))
lassen ein Diffusionsmodell direkt auf dem Grundrissbild arbeiten — das sieht gut aus,
aber Wände "driften": Proportionen stimmen nicht exakt mit der Zeichnung überein.
Für eine Immobilienanzeige ist das ein Haftungsrisiko, kein Feature.

Dieses Projekt trennt Geometrie und Pixel strikt (siehe [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)):

1. **Parsen**: Ein Vision-LLM liest Wände, Türen, Fenster, Räume, Maßstab aus dem
   Grundriss — kalibriert gegen echte Bau-/Zeichnungsnormen ([docs/STANDARDS.md](docs/STANDARDS.md)).
2. **Exakte 3D-Geometrie**: Deterministisch (nicht generativ) aus den geparsten
   Koordinaten extrudiert — garantiert maßtreu.
3. **Fotorealismus**: Ein Diffusionsmodell veredelt nur Material/Licht/Stil auf der
   bereits fixierten Geometrie (Depth-Konditionierung) — kann keine Wand verschieben.
4. **3D-Tour**: Nutzt exakt dasselbe 3D-Modell wie das Rendering — keine zweite,
   abweichende Darstellung.

## Live getestet

Der komplette Durchlauf (Upload → Vision-Parsing → 3D-Modell → fotorealistisches
Rendering) wurde end-to-end mit echten APIs verifiziert — siehe
[backend/README.md](backend/README.md) für den Teststand und welche Provider
bereits live liefen vs. implementiert-aber-ungetestet sind.

## Struktur

```
backend/   FastAPI: Parsing, Geometrie-Builder, Rendering, Projekt-API
frontend/  Next.js: Upload, Grundriss-/Geometrie-Ansicht, begehbare 3D-Tour
docs/      Architektur, Wettbewerbsanalyse, Normen-Referenz, LLM-Entscheidung
```

## Schnellstart

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Keys eintragen
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
DISPLAY=:99 uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (neues Terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev -- --port 3001
```

Details: [backend/README.md](backend/README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/LLM-DECISION.md](docs/LLM-DECISION.md).

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline, Backend-/Frontend-Struktur, ehrlicher MVP-Stand, Roadmap |
| [docs/LLM-DECISION.md](docs/LLM-DECISION.md) | Welches Modell wofür, austauschbare Provider (Claude/Gemini/Replicate) |
| [docs/STANDARDS.md](docs/STANDARDS.md) | DIN/ISO/IFC-Normen, die der Parser als Kontext nutzt |
| [docs/COMPETITORS.md](docs/COMPETITORS.md) | Wettbewerbsanalyse, Open-Source-Bausteine, Differenzierung |
