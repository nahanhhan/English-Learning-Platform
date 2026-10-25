from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..services.speech import SpeechService, SpeechUnavailable, get_speech_service

router = APIRouter(prefix="/api/speech", tags=["speech"])


class SpeechBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    accent: Literal["us", "uk"] = "us"


@router.post("")
async def speech(body: SpeechBody, service: SpeechService = Depends(get_speech_service)):
    try:
        audio = await service.audio(body.text, body.accent)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except SpeechUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return FileResponse(audio.path, media_type="audio/mpeg", headers={
        "X-Speech-Voice": audio.voice, "X-Speech-Cache": "HIT" if audio.cached else "MISS",
    })
