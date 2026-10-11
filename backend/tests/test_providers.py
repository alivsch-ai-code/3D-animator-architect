"""Reine Logiktests fuer die Provider-Auswahl (kein Netzwerk/API-Call) -
siehe docs/LLM-DECISION.md fuer die Provider-Uebersicht.
"""
from app.core.config import get_settings
from app.pipeline.parser import (
    ClaudeFloorPlanParser,
    GeminiFloorPlanParser,
    get_parser,
)
from app.pipeline.render import SimplePreviewRenderer, get_renderer


def test_get_parser_defaults_to_claude(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    assert isinstance(get_parser(), ClaudeFloorPlanParser)
    get_settings.cache_clear()


def test_get_parser_selects_gemini(monkeypatch):
    monkeypatch.setenv("PARSER_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    assert isinstance(get_parser(), GeminiFloorPlanParser)
    get_settings.cache_clear()


def test_get_renderer_defaults_to_preview(monkeypatch):
    monkeypatch.setenv("RENDER_PROVIDER", "preview")
    get_settings.cache_clear()
    assert isinstance(get_renderer(), SimplePreviewRenderer)
    get_settings.cache_clear()
