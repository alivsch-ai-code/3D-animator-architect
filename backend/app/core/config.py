from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Parser-Provider (Grundriss-Vision -> strukturiertes JSON) ---
    # "claude" (empfohlen, siehe docs/LLM-DECISION.md) | "gemini" | "replicate"
    parser_provider: str = "claude"

    anthropic_api_key: str = ""
    parser_model: str = "claude-opus-5"
    chat_model: str = "claude-sonnet-5"

    gemini_api_key: str = ""
    gemini_parser_model: str = "gemini-3-pro"

    replicate_api_token: str = ""
    # Replicate hostet auch proprietaere Modelle wie Claude/Gemini direkt -
    # kein separater Anthropic-/Google-Key noetig. Claude Opus 4.6 ist auf
    # dem Referenzgrundriss auf plausible Geometrie getestet; siehe
    # docs/LLM-DECISION.md fuer Vergleichsergebnisse und Alternativen.
    replicate_parser_model: str = "anthropic/claude-opus-4.6"

    # --- Render-Provider (fotorealistische Veredelung auf fixierter Geometrie) ---
    # "preview" (GPU-frei, kein API-Key, siehe render.py) | "replicate"
    render_provider: str = "preview"
    # FLUX.1 Depth [dev]: nimmt eine Depth-Map + Prompt, haelt Geometrie fest.
    replicate_image_model: str = "google/nano-banana"

    storage_dir: Path = BACKEND_DIR / "data"
    standards_doc_path: Path = REPO_ROOT / "docs" / "STANDARDS.md"

    # Deployment-spezifische Origins (z.B. die oeffentliche Server-IP) gehoeren
    # in .env (CORS_ORIGINS=["http://<ip>:3001"]), nicht fest in den Code.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
