"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { STATUS_LABELS } from "@/lib/types";
import GeometryPanel from "@/components/GeometryPanel";
import TourViewer from "@/components/TourViewer";

export default function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"model" | "render" | null>(null);
  const [stylePrompt, setStylePrompt] = useState(
    "modern scandinavian interior, warm daylight, photorealistic",
  );

  async function refresh() {
    try {
      setProject(await api.getProject(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function handleGenerateModel() {
    setBusy("model");
    try {
      await api.generateModel(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "3D-Modell-Erzeugung fehlgeschlagen");
    } finally {
      setBusy(null);
    }
  }

  async function handleRender() {
    setBusy("render");
    try {
      await api.renderPreview(id, stylePrompt);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rendering fehlgeschlagen");
    } finally {
      setBusy(null);
    }
  }

  if (error && !project) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-10">
        <Link href="/" className="text-sm text-neutral-500">
          ← Zurück
        </Link>
        <p className="text-red-600 mt-4">{error}</p>
      </div>
    );
  }

  if (!project) {
    return <div className="max-w-5xl mx-auto px-6 py-10 text-neutral-500">Lädt…</div>;
  }

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="border-b border-neutral-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <Link href="/" className="text-sm text-neutral-500">
              ← Alle Projekte
            </Link>
            <h1 className="text-xl font-semibold">{project.name}</h1>
          </div>
          <span className="text-sm rounded-full bg-neutral-100 px-3 py-1">
            {STATUS_LABELS[project.status]}
          </span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 flex flex-col gap-10">
        {error && <p className="text-sm text-red-600">{error}</p>}

        <section className="grid md:grid-cols-2 gap-8">
          <div>
            <h2 className="text-lg font-medium mb-3">2D-Grundriss</h2>
            {project.floorplan_filename ? (
              <Image
                src={api.floorplanUrl(id)}
                alt="Hochgeladener Grundriss"
                width={600}
                height={450}
                unoptimized
                className="w-full rounded-lg border border-neutral-200 bg-white"
              />
            ) : (
              <p className="text-sm text-neutral-500">Kein Grundriss hochgeladen.</p>
            )}
          </div>

          <div>
            <h2 className="text-lg font-medium mb-3">Geparste Geometrie</h2>
            {project.geometry ? (
              <GeometryPanel geometry={project.geometry} />
            ) : (
              <p className="text-sm text-neutral-500">
                Noch nicht analysiert{project.status === "failed" ? " (Parsing fehlgeschlagen)" : ""}.
              </p>
            )}
          </div>
        </section>

        {project.geometry && (
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-medium">3D-Modell & begehbare Tour</h2>
              <button
                onClick={handleGenerateModel}
                disabled={busy !== null}
                className="rounded-md bg-neutral-900 text-white px-4 py-2 text-sm font-medium hover:bg-neutral-700 disabled:opacity-50"
              >
                {busy === "model"
                  ? "Erzeuge 3D-Modell…"
                  : project.model_glb_path
                    ? "3D-Modell neu erzeugen"
                    : "3D-Modell erzeugen"}
              </button>
            </div>
            {project.model_glb_path ? (
              <TourViewer modelUrl={api.modelUrl(id)} />
            ) : (
              <p className="text-sm text-neutral-500">
                Noch kein 3D-Modell erzeugt. Die Geometrie oben wird 1:1 (exakte Maße) in ein
                begehbares 3D-Modell umgewandelt — siehe docs/ARCHITECTURE.md.
              </p>
            )}
          </section>
        )}

        {project.model_glb_path && (
          <section>
            <h2 className="text-lg font-medium mb-3">Fotorealistisches Rendering</h2>
            <div className="flex flex-col gap-3 max-w-xl">
              <input
                className="rounded-md border border-neutral-300 px-3 py-2 text-sm"
                value={stylePrompt}
                onChange={(e) => setStylePrompt(e.target.value)}
                placeholder="Stilbeschreibung, z.B. 'modern, warmes Licht, Eichenparkett'"
              />
              <button
                onClick={handleRender}
                disabled={busy !== null}
                className="self-start rounded-md bg-neutral-900 text-white px-4 py-2 text-sm font-medium hover:bg-neutral-700 disabled:opacity-50"
              >
                {busy === "render" ? "Rendere…" : "Vorschau rendern"}
              </button>
            </div>

            {project.render_preview_paths.length > 0 && (
              <div className="grid sm:grid-cols-2 gap-4 mt-5">
                {project.render_preview_paths.map((_, i) => (
                  <Image
                    key={i}
                    src={api.previewUrl(id, i)}
                    alt={`Render-Vorschau ${i + 1}`}
                    width={600}
                    height={450}
                    unoptimized
                    className="w-full rounded-lg border border-neutral-200"
                  />
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
