from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ClassroomEntry as Entry, ClassroomGroup as Group, ClassroomSession as Round
from ..services import classroom as service
from ..services.classroom_import import extract_file, parse_text

router = APIRouter(prefix="/api/classroom", tags=["classroom"])
Kind = Literal["all", "word", "phrase"]
Source = Literal["normal", "mistake"]


class GroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class EntryBody(BaseModel):
    group_id: int
    item_type: Literal["word", "phrase"]
    english: str = Field(max_length=300)
    translation: str = Field(max_length=5000)
    source: str = ""


@router.get("/groups")
def groups(db: Session = Depends(get_db)):
    entries = db.query(Entry).all()
    return [{"id": g.id, "name": g.name,
             "total": sum(e.group_id == g.id for e in entries),
             "mistakes": sum(e.group_id == g.id and e.in_mistake_book for e in entries),
             "words": sum(e.group_id == g.id and e.item_type == "word" for e in entries),
             "phrases": sum(e.group_id == g.id and e.item_type == "phrase" for e in entries),
             "word_mistakes": sum(e.group_id == g.id and e.item_type == "word" and e.in_mistake_book for e in entries),
             "phrase_mistakes": sum(e.group_id == g.id and e.item_type == "phrase" and e.in_mistake_book for e in entries)}
            for g in db.query(Group).order_by(Group.id)]


def save_group(db, body, group_id=None):
    name = body.name.strip()
    if not name:
        raise service.ClassroomError("分组名称不能为空")
    group = db.get(Group, group_id) if group_id else Group()
    if group is None:
        raise service.ClassroomError("分组不存在", 404)
    group.name = name
    db.add(group)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise service.ClassroomError("已有同名分组", 409) from exc
    return {"id": group.id, "name": group.name}


@router.post("/groups")
def create_group(body: GroupBody, db: Session = Depends(get_db)):
    return save_group(db, body)


@router.put("/groups/{group_id}")
def update_group(group_id: int, body: GroupBody, db: Session = Depends(get_db)):
    return save_group(db, body, group_id)


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise service.ClassroomError("分组不存在", 404)
    db.query(Entry).filter_by(group_id=group_id).delete()
    db.delete(group)
    db.commit()
    return {"ok": True}


@router.get("/entries")
def entries(group_id: int | None = None, item_type: Kind = "all", search: str = "",
            mistakes: bool = False, page: int = 1, page_size: int = 30,
            db: Session = Depends(get_db)):
    q = service.filtered(db, group_id, item_type, search, mistakes)
    page, page_size = max(1, page), max(1, min(100, page_size))
    return {"total": q.count(), "page": page,
            "items": [service.entry_payload(db, e) for e in q.offset((page - 1) * page_size).limit(page_size)]}


@router.post("/entries")
def create_entry(body: EntryBody, db: Session = Depends(get_db)):
    return service.entry_payload(db, service.save_entry(db, body.model_dump()))


@router.put("/entries/{entry_id}")
def update_entry(entry_id: int, body: EntryBody, db: Session = Depends(get_db)):
    return service.entry_payload(db, service.save_entry(db, body.model_dump(), entry_id))


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise service.ClassroomError("词条不存在", 404)
    db.delete(entry)
    db.commit()
    return {"ok": True}


class TextBody(BaseModel):
    text: str


@router.post("/imports/text")
def preview_text(body: TextBody):
    return {"rows": parse_text(body.text), "raw_text": body.text}


@router.post("/imports/file")
async def preview_file(request: Request, filename: str):
    # 原始文件请求体，无需 multipart 中转或把用户文件持久化到静态目录。
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 30 * 1024 * 1024:
            raise service.ClassroomError("文件过大，请按课程拆分为 30 MB 以内后导入", 413)
        chunks.append(chunk)
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(extract_file, b"".join(chunks), filename)


class ImportBody(BaseModel):
    rows: list[EntryBody] = Field(max_length=5000)


@router.post("/imports/confirm")
def confirm_import(body: ImportBody, db: Session = Depends(get_db)):
    added, skipped = 0, 0
    try:
        for row in body.rows:
            try:
                service.save_entry(db, row.model_dump(), commit=False)
                added += 1
            except service.ClassroomError as exc:
                if exc.status == 409:
                    skipped += 1
                else:
                    raise
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"added": added, "skipped": skipped}


@router.get("/sessions/current")
def current(group_id: int | None = None, item_type: Kind = "all", source: Source = "normal",
            db: Session = Depends(get_db)):
    session = db.query(Round).filter_by(scope=service.scope_key(group_id, item_type, source)).first()
    return service.session_payload(db, session) if session else None


class StartBody(BaseModel):
    group_id: int | None = None
    item_type: Kind = "all"
    source: Source = "normal"
    restart: bool = False


@router.post("/sessions")
def start(body: StartBody, db: Session = Depends(get_db)):
    return service.start(db, **body.model_dump())


class ActionBody(BaseModel):
    question_id: int
    version: int
    request_id: str = Field(min_length=1, max_length=100)
    action: Literal["choice", "spell", "next"]
    value: str = Field(default="", max_length=5000)


@router.post("/sessions/{session_id}/actions")
def action(session_id: int, body: ActionBody, db: Session = Depends(get_db)):
    return service.act(db, session_id, **body.model_dump())
