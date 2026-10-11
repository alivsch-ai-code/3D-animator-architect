# Frontend

Next.js 16 (App Router, TypeScript, Tailwind) + react-three-fiber für die
begehbare 3D-Tour. Siehe [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Setup

```bash
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev -- --port 3001
```

`cacheComponents`/`partialPrefetching` (Next 16 experimentelles Caching) sind in
`next.config.ts` bewusst deaktiviert: Projektdaten kommen immer live vom Backend,
Standard-`dynamic`-Rendering ist hier vorhersagbarer als das neue Cache-Modell.

## Seiten

- `/` — Projektliste + neues Projekt anlegen (Grundriss-Upload)
- `/projects/[id]` — Grundriss, geparste Geometrie inkl. Normprüfungs-Hinweise,
  3D-Modell generieren, begehbare Tour (`components/TourViewer.tsx`,
  WASD + Pointer-Lock), fotorealistisches Rendering anstoßen

## Build

```bash
npm run build && npm start
```
