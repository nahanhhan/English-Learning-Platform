from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SrsCard, Word
from ..services import study

router = APIRouter(prefix="/api/vocab", tags=["vocab"])


@router.get("/books")
def books(item_type: str = "word", db: Session = Depends(get_db)):
    return study.book_progress(db, item_type)


@router.get("/queue")
def queue(book: str, item_type: str = "word", source: str = "normal",
          db: Session = Depends(get_db)):
    return study.study_queue(db, item_type, book, source)


@router.get("/mistakes")
def mistakes(book: str, item_type: str = "word", db: Session = Depends(get_db)):
    return study.mistake_list(db, item_type, book)


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
def browse(book: str, item_type: str = "word", search: str = "", status: str = "all",
           starred: bool | None = None, page: int = 1, page_size: int = 30,
           db: Session = Depends(get_db)):
    return study.browse(db, item_type, book, search, status, starred, page, page_size)


class CustomWordBody(BaseModel):
    headword: str
    translation: str
    phonetic_us: str = ""
    definition: str = ""


@router.post("/custom")
def add_custom(body: CustomWordBody, db: Session = Depends(get_db)):
    from datetime import date
    hw = body.headword.strip()
    if not hw or not body.translation.strip():
        raise HTTPException(400, "单词和释义不能为空")
    w = Word(book="custom", headword=hw, phonetic_us=body.phonetic_us.strip(),
             translation=body.translation.strip(), definition=body.definition.strip(),
             tags="custom", freq=99)
    db.add(w)
    db.flush()
    db.add(SrsCard(item_type="word", item_id=w.id, book="custom", status="new",
                   due=date.today(), added_at=date.today()))
    db.commit()
    return {"id": w.id}


@router.delete("/custom/{word_id}")
def delete_custom(word_id: int, db: Session = Depends(get_db)):
    w = db.get(Word, word_id)
    if w is None or w.book != "custom":
        raise HTTPException(404, "词条不存在或不可删除")
    db.query(SrsCard).filter(SrsCard.item_type == "word", SrsCard.item_id == word_id).delete()
    db.delete(w)
    db.commit()
    return {"ok": True}


@router.get("/quiz")
def quiz(book: str, item_type: str = "word", count: int = 10, direction: str = "e2c",
         db: Session = Depends(get_db)):
    return study.make_quiz(db, item_type, book, count, direction)
