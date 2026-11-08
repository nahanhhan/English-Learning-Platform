"""短句翻译独立练习、批改版本及北京时间跨日复习。"""
import json
import math
import random
import uuid
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import (AiProvider, ShortAttempt, ShortProgress, ShortQuestion, ShortRun, UserSetting,
                      AccumulationGroup, AccumulationEntry)
from . import ai_client, ai_profiles
from .cet6_translation import RUBRIC_VERSION, band_for_score, system_prompt, require_score_reason
from .classroom import ClassroomError, save_entry, normalize

PASS_SCORE = 12
EXIT_STREAK = 3


def today():
    return datetime.now(timezone(timedelta(hours=8))).date()


def public_question(data):
    return {key: data[key] for key in ('id', 'title', 'topic', 'sentences', 'source')}


def question_list(db, topic='', state='all', search=''):
    questions = db.query(ShortQuestion).order_by(ShortQuestion.id).all()
    done = (db.query(ShortAttempt, ShortRun).join(ShortRun, ShortAttempt.run_id == ShortRun.id)
            .filter(ShortAttempt.status == 'done', ShortAttempt.mock.is_(False))
            .order_by(ShortAttempt.id).all())
    first, latest = {}, {}
    for attempt, run in done:
        if not attempt.is_revision:
            first.setdefault(run.question_id, attempt.score)
        latest[run.question_id] = attempt.score
    progress = {p.question_id: p for p in db.query(ShortProgress)}
    items = []
    for question in questions:
        data = json.loads(question.data_json)
        p = progress.get(question.id)
        reviewed = bool(p and p.in_review)
        completed = question.id in first
        if topic and question.topic != topic:
            continue
        if search and search.casefold() not in (question.title + ''.join(data['sentences'])).casefold():
            continue
        if state == 'unseen' and completed or state == 'review' and not reviewed:
            continue
        items.append({**public_question(data), 'completed': completed, 'in_review': reviewed,
                      'streak': p.streak if p else 0, 'first_score': first.get(question.id),
                      'latest_score': latest.get(question.id)})
    return items


def statistics(db):
    items = question_list(db)
    done = [q for q in items if q['completed']]
    return {'total': len(items), 'completed': len(done), 'unseen': len(items) - len(done),
            'review': sum(q['in_review'] for q in items),
            'first_average': round(sum(q['first_score'] for q in done) / len(done), 1) if done else None,
            'latest_average': round(sum(q['latest_score'] for q in done) / len(done), 1) if done else None,
            'topics': sorted({q['topic'] for q in items}), 'performance': done}


def begin(db, question_id=None, mode='new', topic=''):
    if question_id is None:
        candidates = question_list(db, topic=topic, state='review' if mode == 'review' else 'unseen')
        # 正在作答或等待批改的题不再次自动抽取。
        active = {qid for (qid,) in db.query(ShortRun.question_id).join(ShortAttempt, ShortAttempt.run_id == ShortRun.id)
                  .filter(ShortAttempt.status.in_(['pending', 'grading']))}
        pool = [q for q in candidates if q['id'] not in active]
        if not pool:
            raise ClassroomError('当前没有可抽取的题目；可从题库选题或继续未完成的练习')
        question_id = random.choice(pool)['id']
    question = db.get(ShortQuestion, question_id)
    if question is None:
        raise ClassroomError('题目不存在', 404)
    run = ShortRun(id=str(uuid.uuid4()), question_id=question_id, snapshot=question.data_json,
                   is_review=mode == 'review')
    db.add(run)
    db.commit()
    return run_payload(db, run)


def attempt_payload(attempt):
    return {'id': attempt.id, 'run_id': attempt.run_id, 'content': attempt.content,
            'is_revision': attempt.is_revision, 'status': attempt.status,
            'score': attempt.score if attempt.status == 'done' else None,
            'result': json.loads(attempt.result_json) if attempt.status == 'done' else None,
            'profile': json.loads(attempt.profile_json), 'mock': attempt.mock,
            'error': attempt.error, 'created_at': attempt.created_at.isoformat()}


def run_payload(db, run):
    attempts = db.query(ShortAttempt).filter_by(run_id=run.id).order_by(ShortAttempt.id).all()
    data = json.loads(run.snapshot)
    progress = db.get(ShortProgress, run.question_id)
    return {'id': run.id, 'question': public_question(data), 'is_review': run.is_review,
            'attempts': [attempt_payload(a) for a in attempts],
            'in_review': bool(progress and progress.in_review), 'streak': progress.streak if progress else 0,
            'reference': data['reference'] if any(a.status == 'done' for a in attempts) else None,
            'training_points': data['training_points'] if any(a.status == 'done' for a in attempts) else []}


def submit(db, run_id, content, request_id, provider_id=None):
    content = content.strip()
    if not content:
        raise ClassroomError('请输入完整译文')
    previous = db.query(ShortAttempt).filter_by(request_id=request_id).first()
    if previous:
        if previous.run_id != run_id or previous.content != content or previous.requested_provider_id != provider_id:
            raise ClassroomError('请求编号已被其他作答使用，请重新提交', 409)
        return previous, False
    run = db.get(ShortRun, run_id)
    if run is None:
        raise ClassroomError('练习不存在', 404)
    # 条件更新获取写锁，防止连续点击创建两个首答。
    claimed = db.execute(update(ShortRun).where(ShortRun.id == run.id, ShortRun.version == run.version)
                         .values(version=run.version + 1).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        raise ClassroomError('练习已更新，请读取当前记录后重试', 409)
    if db.query(ShortAttempt).filter(ShortAttempt.run_id == run.id, ShortAttempt.status.in_(['pending', 'grading'])).count():
        db.rollback()
        raise ClassroomError('这道题正在批改，请等待结果', 409)
    provider = db.get(AiProvider, provider_id) if provider_id is not None else (
        db.query(AiProvider).filter_by(is_default=True).first() or db.query(AiProvider).first())
    if provider_id is not None and provider is None:
        db.rollback()
        raise ClassroomError('所选服务商不存在，请重新选择', 404)
    profile = ai_profiles.config(provider) if provider else {}
    profile.pop('api_key', None)
    if provider:
        profile['provider_id'] = provider.id
    mock = db.get(UserSetting, 'mock_mode')
    attempt = ShortAttempt(run_id=run.id, request_id=request_id, content=content,
                           requested_provider_id=provider_id, provider_id=provider.id if provider else None,
                           profile_json=json.dumps(profile, ensure_ascii=False),
                           mock=bool(mock and mock.value == '1'),
                           is_revision=bool(db.query(ShortAttempt).filter_by(run_id=run.id, status='done').count()))
    db.add(attempt)
    db.commit()
    return attempt, True


def build_messages(data, content, previous=None):
    shape = {'score': 0, 'overall_comment': '总体评价', 'score_reason': '整体定档的证据与依据',
             'dimensions': {'accuracy': 4, 'language': 4, 'fluency': 4},
             'sentence_comments': [{'sentence_index': 1, 'translation': '原作答中对应的原文片段或空字符串',
                                    'comment': '对应原句的点评', 'errors': ['确实有误的问题'],
                                    'improvements': ['正确但可优化之处'], 'suggestion': '修改建议'}],
             'improved_version': '保留学习者表达思路的完整修改版',
             'key_notes': [{'expr': '英文表达', 'translation': '简明中文释义', 'note': '用法说明', 'item_type': 'phrase'}],
             'resolved_points': ['与上次相比已修正的问题'], 'remaining_points': ['仍需改进的问题']}
    system = system_prompt(shape, short=True)
    body = {'原文逐句': data['sentences'], '参考译文': data['reference'], '必译信息': data['key_points'],
            '训练重点': data['training_points'], '考生作答': content, '上次作答及点评': previous}
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(body, ensure_ascii=False)}]


def validate_result(result, data, content, *, require_reason=False):
    if not isinstance(result, dict):
        raise ai_client.AiError('批改结果格式错误，请重试')
    if require_reason:
        require_score_reason(result)
    score = result.get('score')
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 15:
        raise ai_client.AiError('批改分数不是有效的15分制，请重试')
    for key in ('overall_comment', 'improved_version'):
        if not isinstance(result.get(key), str) or not result[key].strip():
            raise ai_client.AiError('批改内容不完整，请重试')
    comments = result.get('sentence_comments')
    if not isinstance(comments, list) or len(comments) != len(data['sentences']):
        raise ai_client.AiError('逐句点评不完整，请重试')
    indexes = []
    cleaned = []
    compact = ''.join(content.split())
    for item in comments:
        if not isinstance(item, dict) or type(item.get('sentence_index')) is not int or not isinstance(item.get('comment'), str) or not item['comment'].strip():
            raise ai_client.AiError('逐句点评格式不完整，请重试')
        indexes.append(item['sentence_index'])
        quote = item.get('translation', '')
        if not isinstance(quote, str) or quote and ''.join(quote.split()) not in compact:
            raise ai_client.AiError('点评引用的译文未对应原作答，请重试')
        cleaned.append({'sentence_index': item['sentence_index'], 'translation': quote,
                        'comment': item['comment'], 'suggestion': str(item.get('suggestion') or ''),
                        'errors': [v for v in item.get('errors', []) if isinstance(v, str)] if isinstance(item.get('errors'), list) else [],
                        'improvements': [v for v in item.get('improvements', []) if isinstance(v, str)] if isinstance(item.get('improvements'), list) else []})
    if sorted(indexes) != list(range(1, len(data['sentences']) + 1)):
        raise ai_client.AiError('逐句点评编号不完整，请重试')
    dims = result.get('dimensions') or {}
    if not isinstance(dims, dict):
        dims = {}
    dimensions = {}
    for name in ('accuracy', 'language', 'fluency'):
        value = dims.get(name, 0)
        dimensions[name] = round(max(0, min(5, value)), 1) if isinstance(value, (int, float)) and math.isfinite(value) else 0
    notes = []
    for item in result.get('key_notes', []) if isinstance(result.get('key_notes'), list) else []:
        if isinstance(item, dict) and isinstance(item.get('expr'), str):
            notes.append({k: str(item.get(k) or '') for k in ('expr', 'translation', 'note', 'item_type')})
    return {'score': round(score, 1), 'overall_comment': result['overall_comment'], 'dimensions': dimensions,
            'band': band_for_score(score), 'rubric_version': RUBRIC_VERSION, 'score_reason': str(result.get('score_reason') or ''),
            'sentence_comments': sorted(cleaned, key=lambda c: c['sentence_index']), 'improved_version': result['improved_version'],
            'key_notes': notes, **{key: [v for v in result.get(key, []) if isinstance(v, str)]
                if isinstance(result.get(key), list) else [] for key in ('resolved_points', 'remaining_points')}}


def apply_progress(db, run, attempt):
    if attempt.mock:
        return
    progress = db.get(ShortProgress, run.question_id)
    if progress is None:
        progress = ShortProgress(question_id=run.question_id, in_review=False, streak=0)
        db.add(progress)
    date = today()
    if attempt.score < PASS_SCORE:
        progress.in_review, progress.streak, progress.last_count_date = True, 0, date
    elif run.is_review and progress.in_review and progress.last_count_date != date:
        progress.streak += 1
        progress.last_count_date = date
        if progress.streak >= EXIT_STREAK:
            progress.in_review = False


def grade_attempt(db: Session, attempt_id: int):
    claim = db.execute(update(ShortAttempt).where(ShortAttempt.id == attempt_id, ShortAttempt.status == 'pending')
                       .values(status='grading').execution_options(synchronize_session=False))
    db.commit()
    if claim.rowcount != 1:
        return
    attempt = db.get(ShortAttempt, attempt_id)
    db.refresh(attempt)
    run = db.get(ShortRun, attempt.run_id)
    data = json.loads(run.snapshot)
    try:
        if attempt.mock and json.loads(attempt.profile_json).get('service_type') == 'codex':
            raise ai_client.AiError('已开启模拟批改，请在设置中关闭后使用 Codex')
        if attempt.mock:
            result = {'score': 12, 'overall_comment': '模拟批改示例，不代表真实评分，也不计入完成或巩固。',
                      'dimensions': {'accuracy': 4, 'language': 4, 'fluency': 4},
                      'sentence_comments': [{'sentence_index': i, 'translation': '', 'comment': '示例点评，请配置真实AI后独立重练。',
                                             'errors': [], 'improvements': [], 'suggestion': ''} for i in range(1, len(data['sentences']) + 1)],
                      'improved_version': data['reference'], 'key_notes': [], 'resolved_points': [], 'remaining_points': []}
        else:
            provider = db.get(AiProvider, attempt.provider_id) if attempt.provider_id else None
            if provider is None or (not provider.api_key and ai_profiles.service_type(ai_profiles.config(provider)) != 'codex'):
                raise ai_client.AiError('尚未配置有效AI密钥，请在设置页添加后重试；作答已保留')
            profile = {**json.loads(attempt.profile_json), 'api_key': provider.api_key,
                       'session_id': f'short-{run.id}'}
            if ai_profiles.service_type(profile) == 'codex':
                profile['deadline'] = time.monotonic() + 180
            prior = db.query(ShortAttempt).filter(ShortAttempt.run_id == run.id,
                    ShortAttempt.id < attempt.id, ShortAttempt.status == 'done').order_by(ShortAttempt.id.desc()).first()
            previous = {'content': prior.content, 'result': json.loads(prior.result_json)} if prior else None
            reply = ai_client.chat(profile, build_messages(data, attempt.content, previous), max_tokens=32000)
            result = validate_result(ai_client.extract_json(reply), data, attempt.content, require_reason=True)
        # 同一独立练习仅第一次成功反馈可更新复习；模拟反馈也会终止其独立计次资格。
        db.execute(update(ShortRun).where(ShortRun.id == run.id).values(version=ShortRun.version + 1)
                   .execution_options(synchronize_session=False))
        db.refresh(run)
        attempt.score = result['score']
        attempt.result_json = json.dumps(result, ensure_ascii=False)
        attempt.status = 'done'
        if not run.review_applied:
            apply_progress(db, run, attempt)
            run.review_applied = True
        db.commit()
    except Exception as exc:
        db.rollback()
        attempt = db.get(ShortAttempt, attempt_id)
        attempt.status = 'failed'
        attempt.error = str(exc) if isinstance(exc, ai_client.AiError) else '批改失败，作答已保存，可手动重试'
        db.commit()


def run_grading(attempt_id):
    with SessionLocal() as db:
        grade_attempt(db, attempt_id)


def recover_interrupted(db):
    db.query(ShortAttempt).filter(ShortAttempt.status.in_(['pending', 'grading'])).update(
        {'status': 'failed', 'error': '服务重启，批改已中断；作答已保存，请手动重试'}, synchronize_session=False)
    db.commit()


def set_review(db, question_id, enabled):
    if db.get(ShortQuestion, question_id) is None:
        raise ClassroomError('题目不存在', 404)
    progress = db.get(ShortProgress, question_id)
    if progress is None:
        progress = ShortProgress(question_id=question_id, in_review=False, streak=0)
        db.add(progress)
    if progress.in_review != enabled:
        progress.in_review, progress.streak, progress.last_count_date = enabled, 0, None
    db.commit()
    return {'question_id': question_id, 'in_review': progress.in_review, 'streak': progress.streak}


def collect_expression(db, attempt_id, english, translation, item_type, group_id=None):
    attempt = db.get(ShortAttempt, attempt_id)
    if attempt is None or attempt.status != 'done':
        raise ClassroomError('请先完成批改再收藏表达', 404)
    # 串行处理默认分组创建和重复词条，防止连点创建重名分组。
    db.execute(update(ShortAttempt).where(ShortAttempt.id == attempt_id).values(run_id=ShortAttempt.run_id)
               .execution_options(synchronize_session=False))
    duplicate = db.query(AccumulationEntry).filter_by(item_type=item_type, normalized=normalize(english)).first()
    if duplicate:
        db.rollback()
        return {'added': 0, 'skipped': 1}
    run = db.get(ShortRun, attempt.run_id)
    data = json.loads(run.snapshot)
    if group_id is None:
        group = db.query(AccumulationGroup).filter_by(name='短句翻译积累').first()
        if group is None:
            group = AccumulationGroup(name='短句翻译积累')
            db.add(group)
            db.flush()
        group_id = group.id
    try:
        entry = save_entry(db, {'english': english, 'translation': translation, 'item_type': item_type,
                               'group_id': group_id, 'source': f"短句翻译 {data['id']} · {data['title']}"},
                           commit=False, library='accumulation')
        db.commit()
        return {'added': 1, 'skipped': 0, 'entry_id': entry.id}
    except ClassroomError as exc:
        db.rollback()
        if exc.status == 409:
            return {'added': 0, 'skipped': 1}
        raise
