from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.projects import router as projects_router
from app.core.config import get_settings

app = FastAPI(
    title="3D Animator Architect",
    description=(
        "Grundriss (2D) -> exakte 3D-Rekonstruktion, fotorealistisches Rendering "
        "und begehbare 3D-Tour. Siehe /docs/ARCHITECTURE.md im Repo."
    ),
    version="0.1.0",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
