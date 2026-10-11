"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export default function UploadForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(name.trim());
      await api.uploadFloorplan(project.id, file);
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-w-md">
      <div>
        <label className="block text-sm font-medium mb-1">Projektname</label>
        <input
          className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent transition-colors"
          placeholder="z.B. Musterstraße 12, 3-Zimmer-Wohnung"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Grundriss (Bild oder PDF)</label>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="w-full text-sm"
          required
        />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={busy || !file || !name.trim()}
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
