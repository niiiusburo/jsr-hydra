"""
Tests for LLMBrain error normalization and stats visibility.
"""

import asyncio
import importlib.util
from pathlib import Path

import httpx

_MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "brain" / "llm_brain.py"
_SPEC = importlib.util.spec_from_file_location("llm_brain_module", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_LLM_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_LLM_MODULE)

LLMBrain = _LLM_MODULE.LLMBrain


def _make_brain() -> LLMBrain:
    return LLMBrain(
        api_key="test-key",
        model="gpt-4o-mini",
        provider="openai",
        base_url="https://example.invalid/v1/chat/completions",
    )


def test_normalize_error_message_uses_fallback() -> None:
    llm = _make_brain()
    assert llm._normalize_error_message("", fallback="fallback") == "fallback"
    assert llm._normalize_error_message("   ", fallback="fallback") == "fallback"


def test_extract_http_error_detail_prefers_error_message() -> None:
    llm = _make_brain()
    response = httpx.Response(
        status_code=401,
        json={"error": {"message": "Invalid API key"}},
    )
    detail = llm._extract_http_error_detail(response)
    assert detail == "Invalid API key"


def test_build_insight_marks_error_and_stats_reports_last_error() -> None:
    llm = _make_brain()

    ok = llm._build_insight("market_analysis", "All clear")
    err = llm._build_insight("regime_analysis", "[LLM Error][HTTP 429] Too many requests")

    llm._store_insight(ok)
    llm._store_insight(err)

    assert ok.get("is_error") is False
    assert err.get("is_error") is True

    stats = llm.get_stats()
    assert "last_error" in stats
    assert "HTTP 429" in str(stats.get("last_error"))


def test_call_gpt_returns_non_blank_runtime_error(monkeypatch) -> None:
    llm = _make_brain()

    class _FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            raise RuntimeError()

    monkeypatch.setattr(_LLM_MODULE.httpx, "AsyncClient", lambda timeout=30.0: _FailingClient())

    response = asyncio.run(llm._call_gpt("system", "user"))
    assert response is not None
    assert response.startswith("[LLM Error][RuntimeError]")
    assert response.strip() != "[LLM Error][RuntimeError]"
