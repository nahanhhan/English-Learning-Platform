from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AiProvider
from ..services import ai_client, study

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****"
    return key[:4] + "****" + key[-4:]


def _provider_payload(p: AiProvider) -> dict:
    return {"id": p.id, "name": p.name, "base_url": p.base_url,
            "api_key_masked": _mask(p.api_key), "model": p.model, "is_default": p.is_default}


class ProviderBody(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    model: str = ""
    is_default: bool = False


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
                   api_key=body.api_key.strip(), model=body.model.strip())
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
    p.name = body.name.strip() or p.name
    p.base_url = body.base_url.strip() or p.base_url
    p.model = body.model.strip()
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
        {"base_url": p.base_url, "api_key": p.api_key, "model": p.model})
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
