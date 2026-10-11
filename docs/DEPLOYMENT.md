# Deployment (aktueller Stand)

## Live-URLs

- **Frontend**: `http://<server-ip>:3001`
- **Backend/API**: `http://<server-ip>:8000` (`/docs` für OpenAPI-UI)

Die konkrete IP-Adresse ist bewusst nicht in diesem öffentlichen Repo
dokumentiert — sie wird separat (nicht-versioniert) weitergegeben.

Gewählt wurde die Variante "offene Ports per IP" statt Subdomain+SSL, damit sofort
ohne DNS-Abhängigkeit live getestet werden kann (siehe Diskussion unten).
Entsprechend per `ufw` geöffnet (Backend-Port + Frontend-Port, siehe `.env`/lokale
Notizen für die konkreten Portnummern dieses Deployments):

```bash
sudo ufw allow <backend-port>/tcp comment '3D-Animator-Architect backend'
sudo ufw allow <frontend-port>/tcp comment '3D-Animator-Architect frontend'
```

## Wichtig: Dieser Server hostet mehrere Projekte

Der Zielserver läuft bereits mit nginx + Certbot für andere, nicht mit diesem
Repo verbundene Projekte unter eigenen Subdomains. `ufw`-Default-Policy war
vorher nur SSH/80/443 — die neuen Ports sind eine bewusste, mit dem Nutzer
abgestimmte Erweiterung nur für dieses Projekt. Diese bestehenden
nginx-Konfigurationen anderer Projekte wurden **nicht verändert**.

## ⚠️ Aktueller Prozess-Stand ist NICHT persistent

Backend und Frontend laufen aktuell als einfache Hintergrundprozesse
(`uvicorn`/`next dev`), nicht als systemd-Service. Das heißt konkret:

- Nach einem Server-Neustart laufen sie **nicht automatisch** wieder an.
- Beendet sich die startende Arbeits-Session/der Prozessbaum, können die
  Server mit beendet werden.

**Nächster Schritt für echten Dauerbetrieb**: systemd-Units anlegen oder
pm2/supervisor nutzen, plus `next build` + `next start` statt `next dev`
fürs Frontend (Produktions-Build statt Dev-Server mit Hot-Reload). Das wurde
hier bewusst noch nicht gemacht, um nicht unangekündigt dauerhafte
systemd-Services auf einem fremd-/mehrfach-genutzten Server einzurichten —
bei Bedarf gezielt nachziehen.

## Start-Kommandos

```bash
# Virtueller Display fuer den Renderer (einmalig pro Boot)
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &

# Backend
cd backend && source .venv/bin/activate
DISPLAY=:99 uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3001
```

`frontend/.env.local` muss `NEXT_PUBLIC_API_BASE_URL` auf die öffentlich
erreichbare Backend-Adresse setzen (muss bei Domain-/Port-Wechsel angepasst
und das Frontend neu gestartet werden, da `NEXT_PUBLIC_*`-Variablen beim
Build/Start in das Client-Bundle einkompiliert werden). `backend/.env`
entsprechend um `CORS_ORIGINS` mit der Frontend-Origin ergänzen — beide
`.env`-Dateien sind lokal und nicht Teil des Git-Repos.

## Hinweis Port 3000

Der Standard-Port 3000 war beim ersten Start bereits durch einen anderen
Prozess auf dem Zielserver belegt — deshalb läuft dieses Frontend auf einem
alternativen Port (siehe `.env.local` des jeweiligen Deployments).
