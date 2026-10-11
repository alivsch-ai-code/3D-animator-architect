import type { FloorPlanGeometry, Project } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
