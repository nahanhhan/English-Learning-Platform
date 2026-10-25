from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Phrase, SrsCard
from ..services import study

router = APIRouter(prefix="/api/phrases", tags=["phrases"])


@router.get("/books")
def books(db: Session = Depends(get_db)):
    return study.book_progress(db, "phrase")


@router.get("/queue")
def queue(book: str = "exam", source: str = "normal", db: Session = Depends(get_db)):
    return study.study_queue(db, "phrase", book, source)


@router.get("/mistakes")
def mistakes(book: str = "exam", db: Session = Depends(get_db)):
    return study.mistake_list(db, "phrase", book)


class AnswerBody(BaseModel):
    card_id: int
    rating: str


@router.post("/answer")
def answer(body: AnswerBody, db: Session = Depends(get_db)):
    try:
        return study.answer(db, body.card_id, body.rating)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/star")
def star(body: dict, db: Session = Depends(get_db)):
    card = db.get(SrsCard, int(body.get("card_id", 0)))
    if card is None:
        raise HTTPException(404, "卡片不存在")
    card.starred = not card.starred
    db.commit()
    return {"card_id": card.id, "starred": card.starred}


@router.get("/browse")
def browse(book: str = "exam", search: str = "", status: str = "all",
           starred: bool | None = None, page: int = 1, page_size: int = 30,
           db: Session = Depends(get_db)):
    return study.browse(db, "phrase", book, search, status, starred, page, page_size)


class CustomPhraseBody(BaseModel):
    text: str
    translation: str
    note: str = ""


@router.post("/custom")
def add_custom(body: CustomPhraseBody, db: Session = Depends(get_db)):
    from datetime import date
    text = body.text.strip()
    if not text or not body.translation.strip():
        raise HTTPException(400, "短语和释义不能为空")
    p = Phrase(book="custom", text=text, translation=body.translation.strip(),
               note=body.note.strip())
    db.add(p)
    db.flush()
    db.add(SrsCard(item_type="phrase", item_id=p.id, book="custom", status="new",
                   due=date.today(), added_at=date.today()))
    db.commit()
    return {"id": p.id}


@router.delete("/custom/{phrase_id}")
def delete_custom(phrase_id: int, db: Session = Depends(get_db)):
    p = db.get(Phrase, phrase_id)
    if p is None or p.book != "custom":
        raise HTTPException(404, "短语不存在或不可删除")
    db.query(SrsCard).filter(SrsCard.item_type == "phrase", SrsCard.item_id == phrase_id).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/quiz")
def quiz(book: str = "exam", count: int = 10, direction: str = "e2c",
         db: Session = Depends(get_db)):
    return study.make_quiz(db, "phrase", book, count, direction)
