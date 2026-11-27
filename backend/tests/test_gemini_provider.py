"""Google Gemini 官方预设、URL 规整、模型目录刷新与设置接口回归测试。"""
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import Base, get_db
from app.models import AiProvider
from app.routers.settings import router
from app.services import ai_client as client, ai_profiles as profiles


def gemini(**patch):
    return {
        "service_type": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.5-flash-lite",
        "api_key": "AIzaSy-test-not-real",
        "reasoning_mode": "auto",
        "reasoning_effort": "medium",
        **patch,
    }


def complete(content='{"score":13}', reason="stop"):
    return httpx.Response(200, json={"choices": [{"finish_reason": reason, "message": {"content": content}}]})


@pytest.fixture
def wire(monkeypatch):
    calls, replies = [], []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def _send(self, method, url, **kwargs):
            calls.append({"method": method, "url": url, **json.loads(json.dumps(kwargs))})
            value = replies.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        def post(self, url, **kwargs):
            return self._send("post", url, **kwargs)

        def get(self, url, **kwargs):
            return self._send("get", url, **kwargs)

    monkeypatch.setattr(httpx, "Client", Client)
    return calls, replies


def test_gemini_preset_url_headers_and_effort_payload(wire):
    calls, replies = wire
    replies.append(complete())
    result = client.chat(
        gemini(),
        [{"role": "system", "content": "Grade"}, {"role": "user", "content": "Sample"}],
        max_tokens=8000,
    )
    assert json.loads(result) == {"score": 13}
    call = calls[0]
    assert call["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer AIzaSy-test-not-real"
    assert "x-opencode-session" not in call["headers"]
    assert call["json"]["model"] == "gemini-3.5-flash-lite"
    assert call["json"]["reasoning_effort"] == "medium"


def test_gemini_capabilities_and_validation():
    g3 = gemini()
    assert profiles.capabilities(g3)["modes"] == ["auto"]
    assert profiles.capabilities(g3)["levels"] == ["minimal", "low", "medium", "high"]
    g4 = gemini(model="gemini-4-hydrogen", reasoning_effort="xhigh")
    assert profiles.capabilities(g4)["levels"] == ["low", "medium", "high", "xhigh"]
    profiles.validate(g4)

    with pytest.raises(ValueError):
        profiles.validate(gemini(reasoning_effort="xhigh"))
    with pytest.raises(ValueError):
        profiles.validate(gemini(base_url="https://example.invalid/v1beta/openai"))
    with pytest.raises(ValueError):
        profiles.validate(gemini(reasoning_mode="disabled"))

    auto_detected = gemini(service_type="custom")
    assert profiles.service_type(auto_detected) == "gemini"


def test_gemini_refresh_models_strips_models_prefix(wire):
    calls, replies = wire
    replies.append(
        httpx.Response(
            200,
            json={
                "data": [
                    {"id": "models/gemini-3.5-flash-lite", "display_name": "Gemini 3.5 Flash-Lite"},
                    {"id": "models/gemini-4-hydrogen"},
                ]
            },
        )
    )
    models = client.refresh_models(gemini())
    assert calls[0]["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/models"
    assert [m["id"] for m in models] == ["gemini-3.5-flash-lite", "gemini-4-hydrogen"]
    assert models[0]["name"] == "Gemini 3.5 Flash-Lite"


def test_gemini_settings_round_trip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gemini.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router)

    def connection():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = connection
    with TestClient(app) as api:
        options = api.get("/api/settings/provider-options").json()
        preset = next(p for p in options["profiles"] if p["service_type"] == "gemini")
        assert preset["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
        assert preset["model"] == "gemini-3.5-flash-lite"

        created = api.post(
            "/api/settings/providers",
            json={
                "name": "Google Gemini 官方",
                "service_type": "gemini",
                "base_url": preset["base_url"],
                "model": "gemini-4-hydrogen",
                "api_key": "AIzaSy-secret-key-1234",
                "reasoning_mode": "auto",
                "reasoning_effort": "high",
            },
        )
        assert created.status_code == 200, created.text
        data = created.json()
        assert data["service_type"] == "gemini"
        assert "****" in data["api_key_masked"]
        with factory() as db:
            assert db.get(AiProvider, data["id"]).api_key == "AIzaSy-secret-key-1234"
    engine.dispose()
