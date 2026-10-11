import type { FloorPlanGeometry, Project } from "./types";

// Browser-Anfragen (Client-Komponenten) nutzen die oeffentliche Domain.
// Server-seitiges Rendering (Server-Komponenten wie app/page.tsx) laeuft im
// selben Prozess auf demselben Host wie das Backend - dort ueber die oeffentliche
// Domain zu gehen wuerde einen unnoetigen Umweg nach aussen und zurueck machen
// und haengt zudem an der (ggf. verzoegerten) lokalen DNS-Aufloesung dieses
// Servers. API_BASE_URL_INTERNAL (kein NEXT_PUBLIC_-Prefix, landet nie im
// Client-Bundle) adressiert das Backend serverseitig direkt.
export const API_BASE =
  typeof window === "undefined"
    ? (process.env.API_BASE_URL_INTERNAL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000");

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // Antwort war kein JSON - Statustext reicht als Fehlermeldung.
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listProjects: (): Promise<Project[]> =>
    fetch(`${API_BASE}/api/projects`).then((r) => handle(r)),

  createProject: (name: string): Promise<Project> =>
    fetch(`${API_BASE}/api/projects?name=${encodeURIComponent(name)}`, {
      method: "POST",
    }).then((r) => handle(r)),

  getProject: (id: string): Promise<Project> =>
    fetch(`${API_BASE}/api/projects/${id}`).then((r) => handle(r)),

  uploadFloorplan: (id: string, file: File): Promise<Project> => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/api/projects/${id}/floorplan`, {
      method: "POST",
      body: form,
    }).then((r) => handle(r));
  },

  updateGeometry: (id: string, geometry: FloorPlanGeometry): Promise<Project> =>
    fetch(`${API_BASE}/api/projects/${id}/geometry`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(geometry),
    }).then((r) => handle(r)),

  generateModel: (id: string): Promise<Project> =>
    fetch(`${API_BASE}/api/projects/${id}/model`, { method: "POST" }).then((r) =>
      handle(r),
    ),

  modelUrl: (id: string): string => `${API_BASE}/api/projects/${id}/model.glb`,

  floorplanUrl: (id: string): string => `${API_BASE}/api/projects/${id}/floorplan`,

  renderPreview: (id: string, stylePrompt: string): Promise<Project> =>
    fetch(
      `${API_BASE}/api/projects/${id}/render?style_prompt=${encodeURIComponent(
        stylePrompt,
      )}`,
      { method: "POST" },
    ).then((r) => handle(r)),

  previewUrl: (id: string, index: number): string =>
    `${API_BASE}/api/projects/${id}/preview/${index}.png`,
};
