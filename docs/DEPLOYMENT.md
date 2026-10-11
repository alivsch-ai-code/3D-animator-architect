# Deployment (aktueller Stand)

## Live-URL

- **App**: `https://<subdomain-dieses-deployments>` (nginx-Reverse-Proxy mit
  Let's-Encrypt-SSL, `/api/*` → Backend, Rest → Frontend)

Die konkrete Subdomain/IP ist bewusst nicht in diesem öffentlichen Repo
dokumentiert — sie wird separat (nicht-versioniert) weitergegeben, siehe
`docs/DEPLOYMENT.local.md` (gitignored).

**Historie der Entscheidung**: Zunächst wurde direkter IP:Port-Zugriff über
zusätzlich geöffnete `ufw`-Ports versucht — das scheiterte von außen trotz
korrekter lokaler Firewall-Regeln, vermutlich durch eine vorgelagerte
Cloud-Firewall des Hosters, die nur Standardports (22/80/443) durchlässt.
Umgestellt auf Subdomain + nginx-Reverse-Proxy über die ohnehin offenen
Ports 80/443 — das funktioniert zuverlässig, ist sicherer (TLS statt
Klartext, kein zusätzlicher offener Port) und entspricht der Konvention,
die für andere Projekte auf demselben Server bereits verwendet wird.

## Wichtig: Dieser Server hostet mehrere Projekte

Der Zielserver läuft bereits mit nginx + Certbot für andere, nicht mit diesem
Repo verbundene Projekte unter eigenen Subdomains. Die nginx-Konfiguration
für dieses Projekt wurde als zusätzliche, eigenständige Site angelegt;
bestehende Konfigurationen anderer Projekte wurden **nicht verändert**.

## Persistenz: systemd-Services

Backend, Frontend und der virtuelle Display für den Renderer laufen als
systemd-Services und überleben damit Server-Neustarts automatisch
(eingerichtet, nachdem ein Server-Neustart die vorher manuell gestarteten
Dev-Prozesse beendet hatte):

- `3d-architect-xvfb.service` — virtueller X-Display (`Xvfb :99`), Backend
  und Frontend hängen implizit davon ab (Renderer braucht einen OpenGL-Kontext)
- `3d-architect-backend.service` — `uvicorn`, bindet nur auf `127.0.0.1:8000`
  (nginx übernimmt die öffentliche Erreichbarkeit)
- `3d-architect-frontend.service` — Next.js **Produktions-Build**
  (`npm run build` + `next start`, nicht der Dev-Server), bindet auf
  `127.0.0.1:3001`

Die nginx-API-Location setzt `proxy_connect_timeout`, `proxy_send_timeout` und
`proxy_read_timeout` jeweils auf 300 Sekunden, damit lange Grundriss-Parsing-
und Modellierungsanfragen nicht vorzeitig mit einem Gateway-Timeout abbrechen.
Die versionierte Site-Konfiguration liegt unter
[`deploy/nginx/architect.azamatsysteme.fun.conf`](../deploy/nginx/architect.azamatsysteme.fun.conf).

Alle drei sind `enabled` (Autostart) und `Restart=always`. Unit-Dateien unter
`/etc/systemd/system/3d-architect-*.service` auf dem Zielserver.

### Nach Code-Änderungen neu ausrollen

```bash
# Backend
cd backend && sudo systemctl restart 3d-architect-backend

# Frontend (Produktions-Build muss neu gebaut werden)
cd frontend && npm run build && sudo systemctl restart 3d-architect-frontend
```

### Logs / Status

```bash
sudo systemctl status 3d-architect-backend 3d-architect-frontend 3d-architect-xvfb
sudo journalctl -u 3d-architect-backend -f
```

## Konfiguration

`frontend/.env.local`:
- `NEXT_PUBLIC_API_BASE_URL` — öffentliche App-URL, landet im Browser-Bundle
- `API_BASE_URL_INTERNAL` — `http://127.0.0.1:8000`, nur für serverseitiges
  Rendering (Server-Komponenten) genutzt, damit SSR-Requests nicht unnötig
  über die öffentliche Domain/DNS zurück zum selben Host laufen müssen
  (siehe `frontend/lib/api.ts`)

`backend/.env`: `CORS_ORIGINS` muss die öffentliche App-URL enthalten (auch
wenn durch den Reverse-Proxy die meisten Requests ohnehin same-origin sind).

Beide `.env`-Dateien sind lokal auf dem Server und nicht Teil des Git-Repos.
