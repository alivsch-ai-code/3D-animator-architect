# Backend

FastAPI-Service für Grundriss-Parsing, deterministische 3D-Geometrie und
fotorealistisches Rendering. Siehe [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
für die Gesamtarchitektur.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Keys eintragen, siehe docs/LLM-DECISION.md
```

### Zusätzliche System-Pakete (für den `preview`/`replicate`-Renderer)

Der Renderer nutzt trimesh's Offscreen-Renderer (pyglet + OpenGL), um aus dem
exakten 3D-Modell eine Vorschau bzw. eine Depth-Map (für FLUX Depth) zu
erzeugen. Das braucht einen (virtuellen) Display-Server:

```bash
sudo apt-get install -y xvfb libgl1 libglx-mesa0 libglu1-mesa
pip install "pyglet<2"   # trimesh's windowed-Viewer braucht pyglet 1.x

# Beim Serverstart einen virtuellen Display bereitstellen:
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
DISPLAY=:99 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ohne diese Pakete funktionieren Parsing und 3D-Modell-Erzeugung weiterhin
(`/api/projects/{id}/floorplan`, `/api/projects/{id}/model`) — nur der
`/render`-Endpunkt (egal ob `RENDER_PROVIDER=preview` oder `=replicate`)
benötigt den Offscreen-Renderer, da beide die Szene zuerst als Bild/Depth-Map
rastern.

## Starten (Entwicklung)

```bash
DISPLAY=:99 uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API-Docs dann unter `http://<host>:8000/docs`.

## Provider-Konfiguration

Siehe [.env.example](.env.example) und [../docs/LLM-DECISION.md](../docs/LLM-DECISION.md).
Kurzfassung:

- `PARSER_PROVIDER=claude|gemini|replicate` — welches Modell den Grundriss liest
- `RENDER_PROVIDER=preview|replicate` — ob fotorealistisch (Replicate/FLUX Depth)
  oder nur als einfache Vorschau gerendert wird

**Live getesteter Stand (2026-10-11)**: `PARSER_PROVIDER=replicate` +
`RENDER_PROVIDER=replicate` wurden end-to-end mit einem echten Replicate-Token
gegen einen Testgrundriss verifiziert (Upload → Parsing → 3D-Modell → Foto-Render).
`claude` und `gemini` als Parser-Provider sind vollständig implementiert, aber
mangels Testkeys für diese Anbieter **noch nicht live verifiziert** — technisch
sollten sie funktionieren (gleicher Prompt/Schema-Code-Pfad), sind aber vor
Produktivnutzung einmal real zu testen.

## Tests

```bash
pytest tests/ -q
```
