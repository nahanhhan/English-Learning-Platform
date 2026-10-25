import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models import AiProvider, Grading, Question, Submission, UserSetting
from ..services import ai_client
from ..services.grading import FULL_SCORES, grade, mock_grading

router = APIRouter(prefix="/api/practice", tags=["practice"])


def _get_provider(db: Session, provider_id: int | None = None) -> AiProvider | None:
    if provider_id:
        return db.get(AiProvider, provider_id)
    return (db.query(AiProvider).filter(AiProvider.is_default == True).first()  # noqa: E712
            or db.query(AiProvider).first())


class SubmitBody(BaseModel):
    question_id: int | None = None
    # 自由练习字段（question_id 为空时使用）
    exam_type: str = "free"
    q_type: str = "translation"
    title: str = ""
    prompt: str = ""
    source_text: str = ""
    content: str
    provider_id: int | None = None


def _run_grading(submission_id: int, provider_id: int | None):
    """后台任务：执行批改并落库。"""
    db = SessionLocal()
    try:
        sub = db.get(Submission, submission_id)
        if sub is None:
            return
        sub.status = "grading"
        db.commit()
        provider = _get_provider(db, provider_id)
        mock = (db.get(UserSetting, "mock_mode") or None)
        mock_mode = bool(mock and mock.value == "1")
        full = FULL_SCORES.get((sub.exam_type, sub.q_type), 15)
        g = Grading(submission_id=sub.id, full_score=full)
        try:
            if mock_mode or provider is None or not provider.api_key:
                if provider is None and not mock_mode:
                    raise ai_client.AiError("尚未配置 AI 服务商，请到「设置」页添加 API Key")
                result = mock_grading(sub.exam_type, sub.q_type, full)
                g.provider, g.model, g.mock = "模拟批改", "mock", True
            else:
                result = grade(sub.exam_type, sub.q_type, sub.prompt, sub.source_text,
                               sub.content, sub.word_count,
                               {"base_url": provider.base_url, "api_key": provider.api_key,
                                "model": provider.model}, full)
                g.provider, g.model = provider.name, provider.model
            g.score = float(result.get("score", 0))
            g.result_json = json.dumps(result, ensure_ascii=False)
            sub.status = "done"
        except Exception as e:
            g.error = str(e)
            sub.status = "failed"
        db.add(g)
        db.commit()
    except Exception:
        db.rollback()
        sub = db.get(Submission, submission_id)
        if sub:
            sub.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/submit")
def submit(body: SubmitBody, background: BackgroundTasks, db: Session = Depends(get_db)):
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "作答内容不能为空")
    sub = Submission(
        question_id=body.question_id, exam_type=body.exam_type, q_type=body.q_type,
        title=body.title, prompt=body.prompt, source_text=body.source_text,
        content=content, word_count=len(content.split()),
        status="pending",
    )
    if body.question_id:
        q = db.get(Question, body.question_id)
        if q is None:
            raise HTTPException(404, "题目不存在")
        sub.exam_type, sub.q_type = q.exam_type, q.q_type
        sub.title, sub.prompt, sub.source_text = q.title, q.prompt, q.source_text
    db.add(sub)
    db.commit()
    background.add_task(_run_grading, sub.id, body.provider_id)
    return {"submission_id": sub.id, "status": "pending"}


def _grading_payload(g: Grading | None) -> dict | None:
    if g is None:
        return None
    return {
        "id": g.id, "provider": g.provider, "model": g.model, "mock": g.mock,
        "score": g.score, "full_score": g.full_score,
        "result": json.loads(g.result_json) if g.result_json else None,
        "error": g.error, "created_at": str(g.created_at),
    }


@router.get("/history")
def history(exam_type: str | None = None, q_type: str | None = None,
            page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    q = db.query(Submission)
    if exam_type:
        q = q.filter(Submission.exam_type == exam_type)
    if q_type:
        q = q.filter(Submission.q_type == q_type)
    total = q.count()
    rows = (q.order_by(desc(Submission.created_at))
            .offset((page - 1) * page_size).limit(page_size).all())
    ids = [r.id for r in rows]
    gradings = {}
    if ids:
        for g in db.query(Grading).filter(Grading.submission_id.in_(ids)).all():
            gradings.setdefault(g.submission_id, g)
    items = []
    for r in rows:
        g = gradings.get(r.id)
        items.append({
            "id": r.id, "exam_type": r.exam_type, "q_type": r.q_type, "title": r.title,
            "word_count": r.word_count, "status": r.status, "created_at": str(r.created_at),
            "score": g.score if g else None,
            "full_score": g.full_score if g else FULL_SCORES.get((r.exam_type, r.q_type), 15),
        })
    return {"total": total, "page": page, "items": items}


@router.get("/{sid}")
def result(sid: int, db: Session = Depends(get_db)):
    sub = db.get(Submission, sid)
    if sub is None:
        raise HTTPException(404, "提交不存在")
    g = (db.query(Grading).filter(Grading.submission_id == sid)
         .order_by(desc(Grading.id)).first())
    return {
        "submission": {
            "id": sub.id, "question_id": sub.question_id, "exam_type": sub.exam_type,
            "q_type": sub.q_type, "title": sub.title, "prompt": sub.prompt,
            "source_text": sub.source_text, "content": sub.content,
            "word_count": sub.word_count, "status": sub.status, "created_at": str(sub.created_at),
        },
        "grading": _grading_payload(g),
    }


@router.post("/{sid}/regrade")
def regrade(sid: int, background: BackgroundTasks, body: dict | None = None,
            db: Session = Depends(get_db)):
    sub = db.get(Submission, sid)
    if sub is None:
        raise HTTPException(404, "提交不存在")
    sub.status = "pending"
    db.commit()
    provider_id = (body or {}).get("provider_id")
    background.add_task(_run_grading, sid, provider_id)
    return {"submission_id": sid, "status": "pending"}
