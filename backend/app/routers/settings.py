from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
import json
import uuid
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AiProvider
from ..services import ai_client, ai_profiles, study

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****"
    return key[:4] + "****" + key[-4:]


def _provider_payload(p: AiProvider) -> dict:
    return {"id": p.id, "name": p.name, "base_url": p.base_url,
            "api_key_masked": _mask(p.api_key), "model": p.model, "is_default": p.is_default,
            "service_type": ai_profiles.service_type(ai_profiles.config(p)),
            "reasoning_mode": p.reasoning_mode, "reasoning_effort": p.reasoning_effort,
            "capabilities": ai_profiles.capabilities(ai_profiles.config(p)),
            "models": ai_profiles.catalogue(ai_profiles.config(p))}


class ProviderBody(BaseModel):
    name: str = Field(max_length=60)
    base_url: str = Field(max_length=200)
    api_key: str = ""
    model: str = ""
    is_default: bool = False
    service_type: Literal['custom', 'deepseek', 'opencode_go', 'zhipu'] | None = None
    reasoning_mode: Literal['auto', 'enabled', 'disabled'] | None = None
    reasoning_effort: str | None = Field(default=None, max_length=20)


def _configure(p, body):
    if body.service_type is not None:
        p.service_type = body.service_type
    if body.reasoning_mode is not None:
        p.reasoning_mode = body.reasoning_mode
    if body.reasoning_effort is not None:
        p.reasoning_effort = body.reasoning_effort
    if p.reasoning_mode == 'disabled':
        p.reasoning_effort = ''
    try:
        ai_profiles.validate(ai_profiles.config(p))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get('/provider-options')
def provider_options():
    return {'presets': ai_profiles.PRESETS, 'profiles': [
        {**p, 'models': ai_profiles.catalogue(p), 'capabilities': ai_profiles.capabilities(p)} for p in ai_profiles.PRESETS]}


class CapabilityBody(BaseModel):
    provider_id: int | None = None
    service_type: Literal['custom', 'deepseek', 'opencode_go', 'zhipu'] = 'custom'
    base_url: str = Field(default='', max_length=200)
    model: str = Field(default='', max_length=100)


@router.post('/provider-capabilities')
def provider_capabilities(body: CapabilityBody, db: Session = Depends(get_db)):
    saved = db.get(AiProvider, body.provider_id) if body.provider_id else None
    same_service = saved and saved.base_url == body.base_url and ai_profiles.service_type(ai_profiles.config(saved)) == body.service_type
    provider = {**body.model_dump(), 'models_json': saved.models_json if same_service else '[]'}
    return ai_profiles.capabilities(provider)


@router.post('/providers/{pid}/models')
def refresh_provider_models(pid: int, db: Session = Depends(get_db)):
    provider = db.get(AiProvider, pid)
    if provider is None:
        raise HTTPException(404, '服务商不存在')
    try:
        models = ai_client.refresh_models(ai_profiles.config(provider))
    except ai_client.AiError as exc:
        raise HTTPException(400, str(exc)) from exc
    provider.models_json = json.dumps(models, ensure_ascii=False)
    db.commit()
    return _provider_payload(provider)


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    providers = db.query(AiProvider).all()
    prefs = {
        "daily_new_words": study.get_setting(db, "daily_new_words", "20"),
        "daily_new_phrases": study.get_setting(db, "daily_new_phrases", "10"),
        "mock_mode": study.get_setting(db, "mock_mode", "0"),
        "auto_speak": study.get_setting(db, "auto_speak", "1"),
    }
    return {"providers": [_provider_payload(p) for p in providers], "prefs": prefs}


@router.post("/providers")
def add_provider(body: ProviderBody, db: Session = Depends(get_db)):
    if not body.name.strip() or not body.base_url.strip():
        raise HTTPException(400, "名称和 Base URL 不能为空")
    if db.query(AiProvider).filter(AiProvider.name == body.name.strip()).first():
        raise HTTPException(400, "同名服务商已存在")
    p = AiProvider(name=body.name.strip(), base_url=body.base_url.strip(),
                   api_key=body.api_key.strip(), model=body.model.strip(), service_type='custom',
                   reasoning_mode='auto', reasoning_effort='', models_json='[]')
    # 老客户端未提供新字段时，保留原 GLM-4 的默认关闭行为。
    if body.reasoning_mode is None and p.model.lower().startswith('glm-4'):
        p.reasoning_mode = 'disabled'
    _configure(p, body)
    if body.is_default or not db.query(AiProvider).count():
        p.is_default = True
        for other in db.query(AiProvider).all():
            other.is_default = False
    db.add(p)
    db.commit()
    return _provider_payload(p)


@router.put("/providers/{pid}")
def update_provider(pid: int, body: ProviderBody, db: Session = Depends(get_db)):
    p = db.get(AiProvider, pid)
    if p is None:
        raise HTTPException(404, "服务商不存在")
    if (body.base_url.strip() and body.base_url.strip() != p.base_url or
            body.service_type is not None and body.service_type != p.service_type):
        p.models_json = '[]'
    p.name = body.name.strip() or p.name
    p.base_url = body.base_url.strip() or p.base_url
    p.model = body.model.strip()
    _configure(p, body)
    # api_key 留空或为掩码时保留旧值
    if body.api_key.strip() and "****" not in body.api_key:
        p.api_key = body.api_key.strip()
    if body.is_default:
        for other in db.query(AiProvider).filter(AiProvider.id != pid).all():
            other.is_default = False
        p.is_default = True
    db.commit()
    return _provider_payload(p)


@router.delete("/providers/{pid}")
def delete_provider(pid: int, db: Session = Depends(get_db)):
    p = db.get(AiProvider, pid)
    if p is None:
        raise HTTPException(404, "服务商不存在")
    was_default = p.is_default
    db.delete(p)
    db.commit()
    if was_default:
        first = db.query(AiProvider).first()
        if first:
            first.is_default = True
            db.commit()
    return {"ok": True}


@router.post("/providers/{pid}/default")
def set_default(pid: int, db: Session = Depends(get_db)):
    p = db.get(AiProvider, pid)
    if p is None:
        raise HTTPException(404, "服务商不存在")
    for other in db.query(AiProvider).all():
        other.is_default = False
    p.is_default = True
    db.commit()
    return {"ok": True}


@router.post("/providers/{pid}/test")
def test_provider(pid: int, db: Session = Depends(get_db)):
    p = db.get(AiProvider, pid)
    if p is None:
        raise HTTPException(404, "服务商不存在")
    ok, msg = ai_client.test_connection(
        ai_profiles.config(p, f'connection-{p.id}-' + uuid.uuid4().hex))
    return {"ok": ok, "message": msg}


class PrefsBody(BaseModel):
    daily_new_words: int | None = None
    daily_new_phrases: int | None = None
    mock_mode: bool | None = None
    auto_speak: bool | None = None


@router.put("/prefs")
def update_prefs(body: PrefsBody, db: Session = Depends(get_db)):
    if body.daily_new_words is not None:
        study.set_setting(db, "daily_new_words", str(max(1, min(200, body.daily_new_words))))
    if body.daily_new_phrases is not None:
        study.set_setting(db, "daily_new_phrases", str(max(1, min(200, body.daily_new_phrases))))
    if body.mock_mode is not None:
        study.set_setting(db, "mock_mode", "1" if body.mock_mode else "0")
    if body.auto_speak is not None:
        study.set_setting(db, "auto_speak", "1" if body.auto_speak else "0")
    db.commit()
    return {"ok": True}
