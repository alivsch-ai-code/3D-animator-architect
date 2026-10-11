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
    # Vision-LLM auf Replicate als guenstigere/alternative Parsing-Option.
    # Hinweis: Replicate-Modell-Slugs aendern sich; verifiziert am 2026-10-11
    # per `replicate.Client().models.search(...)` gegen die tatsaechlich
    # verfuegbaren Modelle (siehe docs/LLM-DECISION.md).
    replicate_parser_model: str = "lucataco/qwen3-vl-8b-instruct"

    # --- Render-Provider (fotorealistische Veredelung auf fixierter Geometrie) ---
    # "preview" (GPU-frei, kein API-Key, siehe render.py) | "replicate"
    render_provider: str = "preview"
    # FLUX.1 Depth [dev]: nimmt eine Depth-Map + Prompt, haelt Geometrie fest.
    replicate_image_model: str = "black-forest-labs/flux-depth-dev"

    storage_dir: Path = BACKEND_DIR / "data"
    standards_doc_path: Path = REPO_ROOT / "docs" / "STANDARDS.md"

    cors_origins: list[str] = ["http://localhost:3000"]
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
