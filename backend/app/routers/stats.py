from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Grading, Phrase, ReviewLog, Submission, SrsCard, Word
from ..services import srs, study

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    today = date.today()

    # 连续打卡：有 review_log 或 submission 的日期
    dates = set()
    for (d,) in db.query(func.date(ReviewLog.reviewed_at)).distinct().all():
        dates.add(d if isinstance(d, date) else datetime.strptime(str(d), "%Y-%m-%d").date())
    for (d,) in db.query(func.date(Submission.created_at)).distinct().all():
        dates.add(d if isinstance(d, date) else datetime.strptime(str(d), "%Y-%m-%d").date())
    streak = 0
    cur = today
    if today not in dates:
        cur = today - timedelta(days=1)  # 今天还没学则从昨天起算
    while cur in dates:
        streak += 1
        cur -= timedelta(days=1)

    # 今日数据
    today_reviews = (db.query(ReviewLog)
                     .filter(func.date(ReviewLog.reviewed_at) == today).count())
    today_new = (db.query(SrsCard).filter(SrsCard.added_at == today,
                                          SrsCard.status != "new").count())
    today_practice = (db.query(Submission)
                      .filter(func.date(Submission.created_at) == today).count())

    # 词书进度
    word_books = study.book_progress(db, "word")
    phrase_books = study.book_progress(db, "phrase")

    # 批分趋势（有分数的批改）
    trend_rows = (db.query(Grading, Submission)
                  .join(Submission, Grading.submission_id == Submission.id)
                  .filter(Grading.error == "")
                  .order_by(Grading.created_at).all())
    trend = [{
        "date": str(g.created_at.date()), "exam_type": s.exam_type, "q_type": s.q_type,
        "score": g.score, "full_score": g.full_score, "title": s.title or "自由练习",
    } for g, s in trend_rows]

    # 练习计数（按题型）
    practice_counts = dict(
        db.query(Submission.q_type, func.count(Submission.id)).group_by(Submission.q_type).all())

    # 最近练习
    recent_rows = (db.query(Submission).order_by(Submission.created_at.desc()).limit(8).all())
    recent = []
    for r in recent_rows:
        g = (db.query(Grading).filter(Grading.submission_id == r.id)
             .order_by(Grading.id.desc()).first())
        recent.append({
            "id": r.id, "title": r.title or "自由练习", "q_type": r.q_type,
            "exam_type": r.exam_type, "status": r.status,
            "score": g.score if g else None, "full_score": g.full_score if g else None,
            "created_at": str(r.created_at),
        })

    # 待复习
    due_words = (db.query(SrsCard).filter(SrsCard.item_type == "word", SrsCard.status != "new",
                                          SrsCard.due <= today).count())
    due_phrases = (db.query(SrsCard).filter(SrsCard.item_type == "phrase",
                                            SrsCard.status != "new",
                                            SrsCard.due <= today).count())

    return {
        "streak": streak,
        "today": {"reviews": today_reviews, "new_words": today_new,
                   "practices": today_practice},
        "due": {"words": due_words, "phrases": due_phrases},
        "word_books": word_books,
        "phrase_books": phrase_books,
        "trend": trend,
        "practice_counts": practice_counts,
        "recent": recent,
    }
