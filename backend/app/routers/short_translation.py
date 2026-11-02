from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ShortAttempt, ShortRun
from ..services import short_translation as service
from ..services.classroom import ClassroomError

router = APIRouter(prefix='/api/short-translation', tags=['short-translation'])


@router.get('/questions')
def questions(topic: str = '', state: Literal['all', 'unseen', 'review'] = 'all', search: str = '', db: Session = Depends(get_db)):
    return service.question_list(db, topic, state, search)


@router.get('/stats')
def stats(db: Session = Depends(get_db)):
    return service.statistics(db)


class StartBody(BaseModel):
    question_id: str | None = None
    mode: Literal['new', 'review'] = 'new'
    topic: str = ''


@router.post('/runs')
def begin(body: StartBody, db: Session = Depends(get_db)):
    return service.begin(db, **body.model_dump())


@router.get('/runs/{run_id}')
def run(run_id: str, db: Session = Depends(get_db)):
    record = db.get(ShortRun, run_id)
    if record is None:
        raise ClassroomError('练习不存在', 404)
    return service.run_payload(db, record)


class SubmitBody(BaseModel):
    content: str = Field(min_length=1, max_length=15000)
    request_id: str = Field(min_length=1, max_length=100)
    provider_id: int | None = None


@router.post('/runs/{run_id}/attempts')
def submit(run_id: str, body: SubmitBody, background: BackgroundTasks, db: Session = Depends(get_db)):
    attempt, created = service.submit(db, run_id, **body.model_dump())
    if created:
        background.add_task(service.run_grading, attempt.id)
    return {'attempt_id': attempt.id, 'status': attempt.status}


@router.get('/history')
def history(question_id: str | None = None, page: int = 1, db: Session = Depends(get_db)):
    query = db.query(ShortRun)
    if question_id:
        query = query.filter_by(question_id=question_id)
    page = max(1, page)
    rows = query.order_by(ShortRun.created_at.desc()).offset((page - 1) * 20).limit(20).all()
    return {'total': query.count(), 'page': page, 'items': [service.run_payload(db, row) for row in rows]}


class ReviewBody(BaseModel):
    enabled: bool


@router.put('/questions/{question_id}/review')
def review(question_id: str, body: ReviewBody, db: Session = Depends(get_db)):
    return service.set_review(db, question_id, body.enabled)


class CollectBody(BaseModel):
    english: str = Field(min_length=1, max_length=300)
    translation: str = Field(min_length=1, max_length=5000)
    item_type: Literal['word', 'phrase']
    group_id: int | None = None


@router.post('/attempts/{attempt_id}/collect')
def collect(attempt_id: int, body: CollectBody, db: Session = Depends(get_db)):
    return service.collect_expression(db, attempt_id, **body.model_dump())
