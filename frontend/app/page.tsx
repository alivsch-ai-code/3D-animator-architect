import Link from "next/link";
import { api } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/types";
import UploadForm from "@/components/UploadForm";

export const dynamic = "force-dynamic";

export default async function Home() {
  let projects: Awaited<ReturnType<typeof api.listProjects>> = [];
  let loadError: string | null = null;
  try {
    projects = await api.listProjects();
  } catch (err) {
    loadError = err instanceof Error ? err.message : "Backend nicht erreichbar";
  }

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="border-b border-neutral-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-5">
          <h1 className="text-xl font-semibold">3D Animator Architect</h1>
          <p className="text-sm text-neutral-500">
            Grundriss hochladen → exaktes 3D-Modell → fotorealistisches Rendering →
            begehbare 3D-Tour.
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 flex flex-col gap-12">
        <section>
          <h2 className="text-lg font-medium mb-4">Neues Projekt</h2>
          <UploadForm />
        </section>

        <section>
          <h2 className="text-lg font-medium mb-4">Projekte</h2>
          {loadError && (
            <p className="text-sm text-red-600">
              Backend nicht erreichbar ({loadError}). Läuft der Server unter{" "}
              <code>NEXT_PUBLIC_API_BASE_URL</code>?
            </p>
          )}
          {!loadError && projects.length === 0 && (
            <p className="text-sm text-neutral-500">Noch keine Projekte vorhanden.</p>
          )}
          <ul className="flex flex-col gap-2">
            {projects.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/projects/${p.id}`}
                  className="flex items-center justify-between rounded-md border border-neutral-200 bg-white px-4 py-3 hover:border-neutral-400 transition-colors"
                >
                  <span className="font-medium">{p.name}</span>
                  <span className="text-xs text-neutral-500">{STATUS_LABELS[p.status]}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
