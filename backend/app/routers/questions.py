from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Question, Submission
from ..services.question_charts import chart_assets

router = APIRouter(prefix="/api/questions", tags=["questions"])


@router.get("")
def list_questions(
    exam_type: str | None = Query(None),
    q_type: str | None = Query(None),
    year: int | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Question)
    if exam_type:
        q = q.filter(Question.exam_type == exam_type)
    if q_type:
        q = q.filter(Question.q_type == q_type)
    if year:
        q = q.filter(Question.year == year)
    rows = q.order_by(Question.year.desc(), Question.month.desc(), Question.set_no).all()
    counts = dict(
        db.query(Submission.question_id, func.count(Submission.id))
        .filter(Submission.question_id.isnot(None))
        .group_by(Submission.question_id)
        .all()
    )
    return [{
        "id": r.id, "exam_type": r.exam_type, "year": r.year, "month": r.month,
        "set_no": r.set_no, "q_type": r.q_type, "title": r.title,
        "prompt": r.prompt, "source_text": r.source_text,
        "chart_image": r.chart_image, "notes": r.notes,
        **chart_assets(r.chart_image),
        "practice_count": counts.get(r.id, 0),
    } for r in rows]


@router.get("/meta")
def question_meta(db: Session = Depends(get_db)):
    """供筛选器用的元信息：各考试类型的年份/套数。"""
    out = {}
    for et in ("cet6", "ky2"):
        years = [r[0] for r in db.query(distinct(Question.year))
                 .filter(Question.exam_type == et).order_by(Question.year.desc()).all()]
        types = [r[0] for r in db.query(distinct(Question.q_type))
                 .filter(Question.exam_type == et).all()]
        out[et] = {"years": years, "q_types": types}
    return out


@router.get("/{qid}")
def get_question(qid: int, db: Session = Depends(get_db)):
    r = db.get(Question, qid)
    if r is None:
        raise HTTPException(404, "题目不存在")
    return {
        "id": r.id, "exam_type": r.exam_type, "year": r.year, "month": r.month,
        "set_no": r.set_no, "q_type": r.q_type, "title": r.title,
        "prompt": r.prompt, "source_text": r.source_text,
        "chart_image": r.chart_image, "notes": r.notes,
        **chart_assets(r.chart_image),
    }
