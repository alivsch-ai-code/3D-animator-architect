"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

// Es gibt keinen echten Fortschritts-Stream vom Backend (waere SSE/WebSocket,
// siehe docs/ARCHITECTURE.md Roadmap) - diese Stufen laufen rein zeitbasiert
// durch und sollen dem Nutzer nur zeigen, DASS etwas passiert (Analyse kann
// 30-90s dauern), nicht einen exakten Fortschritt vortaeuschen.
const PROGRESS_STAGES = [
  { label: "Datei wird hochgeladen…", pct: 10 },
  { label: "Personenbezogene Daten werden geschwärzt…", pct: 25 },
  { label: "Grundriss wird analysiert (Wände, Türen, Räume)…", pct: 45 },
  { label: "Maße gegen Bau-/Zeichnungsnormen geprüft…", pct: 70 },
  { label: "Ergebnis wird aufbereitet…", pct: 88 },
];

export default function UploadForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!busy) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setStageIndex(0);
      return;
    }
    intervalRef.current = setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, PROGRESS_STAGES.length - 1));
    }, 2800);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [busy]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setAttempted(true);

    if (!name.trim() && !file) {
      setError("Bitte Projektname eingeben und einen Grundriss auswählen.");
      return;
    }
    if (!name.trim()) {
      setError("Bitte einen Projektnamen eingeben.");
      return;
    }
    if (!file) {
      setError("Bitte einen Grundriss (Bild oder PDF) auswählen.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(name.trim());
      await api.uploadFloorplan(project.id, file);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler");
      setBusy(false);
    }
  }

  const nameMissing = attempted && !name.trim();
  const fileMissing = attempted && !file;
  const stage = PROGRESS_STAGES[stageIndex];

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4 max-w-md">
      <div>
        <label className="block text-sm font-medium mb-1">Projektname</label>
        <input
          className={`w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-colors ${
            nameMissing ? "border-red-400" : "border-neutral-300"
          }`}
          placeholder="z.B. Musterstraße 12, 3-Zimmer-Wohnung"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={busy}
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Grundriss (Bild oder PDF)</label>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={busy}
          className={`w-full text-sm rounded-md border p-1.5 ${
            fileMissing ? "border-red-400" : "border-transparent"
          }`}
        />
        <p className="text-xs text-neutral-400 mt-1">
          Namen/Adressen in Schriftfeldern werden automatisch geschwärzt, bevor etwas gespeichert wird.
        </p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {busy && (
        <div className="flex flex-col gap-1.5">
          <div className="h-1.5 w-full rounded-full bg-neutral-200 overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all duration-700 ease-out"
              style={{ width: `${stage.pct}%` }}
            />
          </div>
          <p className="text-xs text-neutral-500">{stage.label}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={busy}
        className="rounded-md bg-accent text-white px-4 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 inline-flex items-center justify-center gap-2"
      >
        {busy && (
          <span className="h-3.5 w-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin" />
        )}
        {busy ? "Analysiere Grundriss…" : "Grundriss hochladen & analysieren"}
      </button>
    </form>
  );
}
