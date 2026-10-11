"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import GeometryPanel from "@/components/GeometryPanel";
import TourViewer from "@/components/TourViewer";
import StatusBadge from "@/components/StatusBadge";
import PipelineSteps from "@/components/PipelineSteps";

function Section({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-neutral-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          {subtitle && <p className="text-sm text-neutral-500 mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

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
    "professional real estate interior photography, realistic furniture and materials, natural daylight, sharp focus, DSLR photograph, 24mm wide-angle lens",
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
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-800">
          ← Zurück
        </Link>
        <p className="text-red-600 mt-4">{error}</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-10 text-neutral-500 flex items-center gap-2">
        <span className="h-3.5 w-3.5 rounded-full border-2 border-neutral-300 border-t-accent animate-spin" />
        Lädt…
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-neutral-200/70 bg-white/70 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4">
          <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-800">
            ← Alle Projekte
          </Link>
          <div className="flex flex-wrap items-center justify-between gap-4 mt-1">
            <h1 className="text-xl font-semibold tracking-tight">{project.name}</h1>
            <div className="flex items-center gap-4">
              <PipelineSteps status={project.status} />
              <StatusBadge status={project.status} />
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 flex flex-col gap-8">
        {error && (
          <p className="text-sm text-red-600 bg-red-50 ring-1 ring-red-200 rounded-md px-4 py-3">
            {error}
          </p>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          <Section title="2D-Grundriss">
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
          </Section>

          <Section
            title="Geparste Geometrie"
            subtitle="Von Claude/Replicate analysiert, gegen Bau-/Zeichnungsnormen geprüft"
          >
            {project.geometry ? (
              <GeometryPanel geometry={project.geometry} />
            ) : (
              <p className="text-sm text-neutral-500">
                Noch nicht analysiert
                {project.status === "failed" ? " (Parsing fehlgeschlagen)" : ""}.
              </p>
            )}
          </Section>
        </div>

        {project.geometry && (
          <Section
            title="3D-Modell & begehbare Tour"
            subtitle="Dasselbe Modell wird auch für das Rendering verwendet — keine Abweichung"
            action={
              <button
                onClick={handleGenerateModel}
                disabled={busy !== null}
                className="rounded-md bg-accent text-white px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 inline-flex items-center gap-2"
              >
                {busy === "model" && (
                  <span className="h-3.5 w-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                )}
                {busy === "model"
                  ? "Erzeuge 3D-Modell…"
                  : project.model_glb_path
                    ? "3D-Modell neu erzeugen"
                    : "3D-Modell erzeugen"}
              </button>
            }
          >
            {project.model_glb_path ? (
              <TourViewer modelUrl={api.modelUrl(id)} rooms={project.geometry?.rooms ?? []} />
            ) : (
              <p className="text-sm text-neutral-500">
                Noch kein 3D-Modell erzeugt. Die Geometrie oben wird 1:1 (exakte Maße) in ein
                begehbares 3D-Modell umgewandelt.
              </p>
            )}
          </Section>
        )}

        {project.model_glb_path && (
          <Section
            title="Fotorealistisches Rendering"
            subtitle="Material, Licht und Stil werden auf der fixierten Geometrie veredelt"
          >
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-colors"
                value={stylePrompt}
                onChange={(e) => setStylePrompt(e.target.value)}
                placeholder="Stilbeschreibung, z.B. 'modern, warmes Licht, Eichenparkett'"
              />
              <button
                onClick={handleRender}
                disabled={busy !== null}
                className="rounded-md bg-accent text-white px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 inline-flex items-center justify-center gap-2 whitespace-nowrap"
              >
                {busy === "render" && (
                  <span className="h-3.5 w-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                )}
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
          </Section>
        )}
      </main>
    </div>
  );
}
