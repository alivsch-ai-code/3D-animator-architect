import Link from "next/link";
import { api } from "@/lib/api";
import UploadForm from "@/components/UploadForm";
import StatusBadge from "@/components/StatusBadge";

export const dynamic = "force-dynamic";

const FEATURES = [
  {
    icon: "📐",
    title: "Maßtreu statt geschätzt",
    text: "Wände, Türen und Fenster werden aus dem Grundriss exakt vermessen und deterministisch nachgebaut — keine KI-Geometrie, die „driftet”.",
  },
  {
    icon: "🧱",
    title: "Echtes 3D-Modell",
    text: "Aus der geparsten Geometrie entsteht ein reales 3D-Modell (GLB) — Grundlage für Rendering und Tour zugleich.",
  },
  {
    icon: "✨",
    title: "Fotorealistisches Rendering",
    text: "Material, Licht und Stil werden auf der fixierten Geometrie veredelt — die Wände bleiben exakt wie im Plan.",
  },
  {
    icon: "🚶",
    title: "Begehbare 3D-Tour",
    text: "Dasselbe Modell lässt sich direkt im Browser begehen — ideal zum Teilen mit Kaufinteressenten.",
  },
];

export default async function Home() {
  let projects: Awaited<ReturnType<typeof api.listProjects>> = [];
  let loadError: string | null = null;
  try {
    projects = await api.listProjects();
  } catch (err) {
    loadError = err instanceof Error ? err.message : "Backend nicht erreichbar";
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-neutral-200/70 bg-white/70 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <span className="font-semibold tracking-tight">3D Animator Architect</span>
          <a
            href="#neues-projekt"
            className="text-sm rounded-full bg-accent text-white px-4 py-1.5 hover:opacity-90 transition-opacity"
          >
            Neues Projekt
          </a>
        </div>
      </header>

      <section className="relative overflow-hidden border-b border-neutral-200/70">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-[radial-gradient(60%_60%_at_80%_0%,var(--accent-soft),transparent)]"
        />
        <div className="max-w-6xl mx-auto px-6 py-20 sm:py-28">
          <p className="text-sm font-medium text-accent mb-3">
            Grundriss → exaktes 3D → Fotorealismus → Tour
          </p>
          <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight max-w-2xl leading-tight">
            Immobilien aus dem Grundriss heraus verkaufen — maßtreu und überzeugend.
          </h1>
          <p className="mt-5 max-w-xl text-neutral-600 text-lg">
            Lade eine 2D-Bauzeichnung hoch. Wir erzeugen daraus ein exaktes 3D-Modell,
            fotorealistische Ansichten und eine begehbare Tour — ohne dass eine einzige
            Wand von der Zeichnung abweicht.
          </p>
          <a
            href="#neues-projekt"
            className="inline-block mt-8 rounded-md bg-accent text-white px-5 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Grundriss hochladen
          </a>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-6 py-16">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm"
            >
              <div className="text-2xl mb-3">{f.icon}</div>
              <h3 className="font-medium mb-1.5">{f.title}</h3>
              <p className="text-sm text-neutral-600 leading-relaxed">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <main className="max-w-6xl mx-auto px-6 pb-24 flex flex-col gap-16">
        <section id="neues-projekt" className="scroll-mt-20">
          <h2 className="text-xl font-semibold mb-1">Neues Projekt</h2>
          <p className="text-sm text-neutral-500 mb-6">
            Projektname vergeben und Grundriss-Bild hochladen — die Analyse startet sofort.
          </p>
          <div className="rounded-xl border border-neutral-200 bg-white p-6 shadow-sm">
            <UploadForm />
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold mb-6">Projekte</h2>
          {loadError && (
            <p className="text-sm text-red-600 bg-red-50 ring-1 ring-red-200 rounded-md px-4 py-3">
              Backend nicht erreichbar ({loadError}). Läuft der Server unter{" "}
              <code>NEXT_PUBLIC_API_BASE_URL</code>?
            </p>
          )}
          {!loadError && projects.length === 0 && (
            <div className="rounded-xl border border-dashed border-neutral-300 bg-white/60 px-6 py-12 text-center">
              <p className="text-neutral-500 text-sm">
                Noch keine Projekte vorhanden. Lade oben deinen ersten Grundriss hoch.
              </p>
            </div>
          )}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="group rounded-xl border border-neutral-200 bg-white p-5 shadow-sm hover:shadow-md hover:border-neutral-300 transition-all"
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <h3 className="font-medium group-hover:text-accent transition-colors">
                    {p.name}
                  </h3>
                  <StatusBadge status={p.status} />
                </div>
                <p className="text-xs text-neutral-500">
                  {p.geometry
                    ? `${p.geometry.rooms.length} Raum(e) · ${p.geometry.walls.length} Wände`
                    : "Noch nicht analysiert"}
                </p>
              </Link>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-neutral-200/70 py-8">
        <div className="max-w-6xl mx-auto px-6 text-xs text-neutral-400">
          3D Animator Architect — Geometrie und Pixel bewusst getrennt, siehe{" "}
          <code>docs/ARCHITECTURE.md</code> im Repository.
        </div>
      </footer>
    </div>
  );
}
