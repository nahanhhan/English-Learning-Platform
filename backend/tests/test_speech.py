import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.routers.speech import router
from app.services import speech

MP3 = b"\xff\xf3" + b"\0" * 1024


@pytest.mark.parametrize("original,expected", [
    ("do sth", "do something"), ("do sth.", "do something"),
    ("stand sb up", "stand somebody up"), ("SB.'s book", "somebody's book"),
    ("sb's book", "somebody's book"), ("sth’s value", "something's value"),
    ("have / get", "have or get"), ("have/get", "have or get"),
    ("sb/sth", "somebody or something"), ("sb./sth.", "somebody or something"),
    ("have / get a shot at (doing) sth", "have or get a shot at doing something"),
    ("be in a / no position to do", "be in a or no position to do"),
    ("compare...with/to...", "compare with or to"),
    ("（do） STH／SB", "do something or somebody"),
    ("splash substance absorbs", "splash substance absorbs"),
    ("SBS something somebody", "SBS something somebody"),
    ("  meet\n sb.\t halfway  ", "meet somebody halfway"),
])
def test_normalize_only_spoken_text(original, expected):
    assert speech.normalize_speech_text(original) == expected


def test_fixed_voice_cache_and_offline_restart(tmp_path):
    calls = []
    async def generate(text, voice, rate, pitch):
        calls.append((text, voice, rate, pitch))
        return MP3
    async def offline(*args):
        raise OSError("offline")
    async def run():
        service = speech.SpeechService(tmp_path, generate)
        first = await service.audio("have / get a shot at (doing) sth")
        assert not first.cached and first.voice == "en-US-JennyNeural"
        assert first.path.read_bytes() == MP3
        cached = await service.audio("have / get a shot at (doing) sth")
        assert cached.cached and cached.path == first.path
        restarted = speech.SpeechService(tmp_path, offline)
        assert (await restarted.audio("have / get a shot at (doing) sth")).cached
        uk = await service.audio("have / get a shot at (doing) sth", "uk")
        assert uk.voice == "en-GB-SoniaNeural" and uk.path != first.path
        assert calls == [
            ("have or get a shot at doing something", "en-US-JennyNeural", "-5%", "+0Hz"),
            ("have or get a shot at doing something", "en-GB-SoniaNeural", "-5%", "+0Hz"),
        ]
    asyncio.run(run())


def test_concurrent_requests_and_one_cancelled_waiter(tmp_path):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def generate(*args):
            calls.append(args)
            started.set()
            await release.wait()
            return MP3
        service = speech.SpeechService(tmp_path, generate)
        first = asyncio.create_task(service.audio("meet sb halfway"))
        await started.wait()
        second = asyncio.create_task(service.audio("meet somebody halfway"))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        result = await second
        assert result.path.read_bytes() == MP3
        assert len(calls) == 1 and len(list(tmp_path.glob("*.mp3"))) == 1
        assert not list(tmp_path.glob("*.part"))
    asyncio.run(run())


def test_partial_stream_failure_never_publishes_cache(tmp_path, monkeypatch):
    class BrokenCommunicate:
        def __init__(self, *args, **kwargs):
            pass
        async def stream(self):
            yield {"type": "audio", "data": MP3}
            raise ConnectionError("stream interrupted after first audio chunk")
    import edge_tts
    monkeypatch.setattr(edge_tts, "Communicate", BrokenCommunicate)
    async def run():
        service = speech.SpeechService(tmp_path)
        with pytest.raises(speech.SpeechUnavailable):
            await service.audio("word")
        assert not list(tmp_path.glob("*"))
        async def recovered(*args):
            return MP3
        service.synthesizer = recovered
        assert (await service.audio("word")).path.read_bytes() == MP3
    asyncio.run(run())


def test_invalid_audio_timeout_and_incomplete_cache_recovery(tmp_path):
    async def empty(*args):
        return b""
    async def slow(*args):
        await asyncio.Event().wait()
    async def complete(*args):
        return MP3
    async def run():
        for synthesizer in (empty, slow):
            service = speech.SpeechService(tmp_path, synthesizer, timeout=.01)
            with pytest.raises(speech.SpeechUnavailable):
                await service.audio("hello")
        path = tmp_path / (speech.cache_key("hello", "us") + ".mp3")
        path.write_bytes(b"ID3")
        result = await speech.SpeechService(tmp_path, complete).audio("hello")
        assert not result.cached and result.path.read_bytes() == MP3
        assert not list(tmp_path.glob("*.part"))
    asyncio.run(run())


def test_profile_and_rule_version_are_part_of_cache_key(monkeypatch):
    original = speech.cache_key("hello", "us")
    assert original != speech.cache_key("hello", "uk")
    monkeypatch.setattr(speech, "RATE", "+0%")
    assert original != speech.cache_key("hello", "us")
    monkeypatch.setattr(speech, "RATE", "-5%")
    monkeypatch.setattr(speech, "PITCH", "+1Hz")
    assert original != speech.cache_key("hello", "us")
    monkeypatch.setattr(speech, "PITCH", "+0Hz")
    monkeypatch.setattr(speech, "RULE_VERSION", "v2")
    assert original != speech.cache_key("hello", "us")


def test_http_audio_cache_validation_and_failure(tmp_path):
    calls = []
    async def synthesize(*args):
        calls.append(args)
        return MP3
    service = speech.SpeechService(tmp_path, synthesize)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[speech.get_speech_service] = lambda: service
    with TestClient(app) as client:
        response = client.post("/api/speech", json={"text": "stand sb up"})
        assert response.status_code == 200 and response.content == MP3
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["X-Speech-Voice"] == "en-US-JennyNeural"
        assert response.headers["X-Speech-Cache"] == "MISS"
        assert client.post("/api/speech", json={"text": "stand somebody up"}).headers["X-Speech-Cache"] == "HIT"
        assert len(calls) == 1
        assert client.post("/api/speech", json={"text": "hello", "accent": "invalid"}).status_code == 422
        assert client.post("/api/speech", json={"text": " ( ) "}).status_code == 400
        async def unavailable(*args):
            raise OSError("offline")
        service.synthesizer = unavailable
        failed = client.post("/api/speech", json={"text": "uncached"})
        assert failed.status_code == 503 and "重试" in failed.json()["detail"]
