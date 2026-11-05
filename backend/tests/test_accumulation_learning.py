"""积累选题权重、独立历史、原数据兼容与真实答题流程。"""
from datetime import datetime, timedelta
from fractions import Fraction
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from test_accumulation import client_db, action
from app.models import AccumulationEntry, AccumulationGroup, AccumulationReviewLog as Log
from app.models import AccumulationSessionItem
from app.services import accumulation_learning as learning
from app.services import classroom as service


def entry(key, completed=5, mistake=False):
    return SimpleNamespace(id=key, completed=completed, in_mistake_book=mistake)


def stats(correct=5, attempts=5, when=datetime(2026, 11, 5)):
    return learning.LearningStats(attempts, correct, min(attempts, 10), min(correct, 10), when)


def test_exact_weights_and_direction():
    entries = [entry(1), entry(2)]
    # 只改变正确率时，低正确率的优先级比高正确率高 60%。
    scores = learning.priorities(entries, {1: stats(0), 2: stats(5)})
    assert scores == {1: Fraction(4, 5), 2: Fraction(1, 5)}
    # 只改变间隔时，久未练习比刚练过高 20%。
    scores = learning.priorities(entries, {1: stats(when=datetime(2026, 10, 1)), 2: stats()})
    assert scores == {1: Fraction(3, 5), 2: Fraction(2, 5)}
    # 只改变练习次数时，少练的比多练的高 20%。
    entries[0].completed = 1
    scores = learning.priorities(entries, {1: stats(), 2: stats()})
    assert scores == {1: Fraction(3, 5), 2: Fraction(2, 5)}
    # 三项冲突仍以 60/20/20 综合决定，而非各抽固定数量。
    scores = learning.priorities([entry(1, 20), entry(2, 1)], {
        1: stats(0), 2: stats(5, when=datetime(2026, 10, 1)),
    })
    assert scores == {1: Fraction(3, 5), 2: Fraction(2, 5)}


def test_average_ties_unknowns_and_stable_selection():
    assert learning._ranks({1: 0, 2: 0, 3: 1}) == {1: Fraction(1, 4), 2: Fraction(1, 4), 3: 1}
    entries = [entry(i) for i in range(65, 0, -1)]
    assert set(learning.priorities(entries, {}).values()) == {Fraction(1, 2)}
    assert [e.id for e in learning.select_entries(entries, {})] == list(range(1, 51))
    assert learning.priorities([entry(1)], {}) == {1: Fraction(1, 2)}
    assert learning.select_entries([], {}) == []
    entries[0].in_mistake_book = True
    assert learning.select_entries(entries, {})[0].id == 65
    assert learning.priorities(entries, {})[65] == Fraction(4, 5)
    assert learning.LearningStats().payload() == {
        'recent_accuracy': None, 'recent_attempts': 0, 'last_practiced_at': None,
    }


def test_recent_ten_dominate_without_erasing_lifetime_history(client_db):
    _, db, factory = client_db
    item = db.query(AccumulationEntry).first()
    other = db.query(AccumulationEntry).filter(AccumulationEntry.id != item.id).first()
    start = datetime(2026, 10, 1)
    for i in range(20):
        db.add(Log(entry_id=item.id, session_id=900, question_id=1000 + i,
            choice_correct=i >= 10, spelling_correct=i >= 10,
            completed_at=start + timedelta(days=i)))
    db.add(Log(entry_id=other.id, session_id=901, question_id=2000,
        choice_correct=True, spelling_correct=False, completed_at=start))
    db.commit()
    with factory() as reopened:
        observed = learning.statistics(reopened, [item.id])[item.id]
        assert observed.attempts == 20 and observed.correct == 10
        assert observed.recent_attempts == observed.recent_correct == 10
        assert observed.accuracy == Fraction(9, 10)
        assert observed.last_practiced_at == start + timedelta(days=19)
        assert observed.payload()['last_practiced_at'].endswith('Z')
        assert learning.statistics(reopened, []) == {}
        assert set(learning.statistics(reopened, [other.id])) == {other.id}
        assert learning.statistics(reopened, [other.id])[other.id].recent_correct == 0


def test_equal_timestamps_use_latest_record_ids_for_recent_ten(client_db):
    _, db, _ = client_db
    item = db.query(AccumulationEntry).first()
    for i in range(12):
        db.add(Log(entry_id=item.id, session_id=900, question_id=1000 + i,
            choice_correct=i >= 2, spelling_correct=True, completed_at=datetime(2026, 11, 5)))
    db.commit()
    observed = learning.statistics(db, [item.id])[item.id]
    assert observed.attempts == 12 and observed.correct == 10
    assert observed.recent_attempts == observed.recent_correct == 10


@pytest.mark.parametrize('source', ['normal', 'mistake'])
def test_api_selects_priority_fifty_from_entire_filtered_pool(client_db, monkeypatch, source):
    client, db, _ = client_db
    group = AccumulationGroup(name='按表现选题')
    db.add(group)
    db.flush()
    ids = []
    for i in range(60):
        item = service.save_entry(db, {'group_id': group.id, 'item_type': 'word',
            'english': f'weightedword{i}', 'translation': f'权重释义{i}'}, commit=False, library='accumulation')
        item.completed, item.in_mistake_book = 1, True
        ids.append(item.id)
        db.add(Log(entry_id=item.id, session_id=900, question_id=1000 + i,
            choice_correct=i < 10, spelling_correct=True, completed_at=datetime(2026, 11, 1)))
    db.commit()
    # 展示打乱不能影响哪些词入选；薄弱的后 50 条全部入选。
    monkeypatch.setattr(service.random, 'shuffle', lambda values: values.reverse())
    body = {'group_id': group.id, 'item_type': 'word', 'source': source}
    session = client.post('/api/accumulation/sessions', json=body).json()
    selected = db.scalars(select(AccumulationSessionItem.entry_id).where(
        AccumulationSessionItem.session_id == session['id']).order_by(AccumulationSessionItem.position)).all()
    assert selected == list(reversed(ids[10:])) and session['total'] == 50
    # 新表现能改变下一轮入选集合，无需新增词条或改动浏览顺序。
    for i in ids[:10]:
        db.add(Log(entry_id=i, session_id=901, question_id=2000 + i,
            choice_correct=False, spelling_correct=False, completed_at=datetime(2026, 11, 5)))
    # 将原薄弱词改为最近已稳定全对，使近期进步及时反映在排名中。
    for i in ids[10:]:
        for j in range(10):
            db.add(Log(entry_id=i, session_id=901, question_id=3000 + i * 10 + j,
                choice_correct=True, spelling_correct=True, completed_at=datetime(2026, 11, 5)))
    db.commit()
    restarted = client.post('/api/accumulation/sessions', json={**body, 'restart': True}).json()
    selected_again = set(db.scalars(select(AccumulationSessionItem.entry_id).where(
        AccumulationSessionItem.session_id == restarted['id'])))
    assert set(ids[:10]) <= selected_again and len(selected_again) == 50
    assert selected_again != set(selected)


@pytest.mark.parametrize('wrong_choice,wrong_spell', [(False, False), (True, False), (False, True), (True, True)])
def test_completed_attempt_is_atomic_once_and_survives_restart(client_db, wrong_choice, wrong_spell):
    client, db, factory = client_db
    group = AccumulationGroup(name='独立记录')
    db.add(group)
    db.flush()
    item = service.save_entry(db, {'group_id': group.id, 'item_type': 'word',
        'english': 'recordedword', 'translation': '独立记录释义'}, commit=False, library='accumulation')
    item.completed = 7
    db.commit()
    listing = client.get(f'/api/accumulation/entries?group_id={group.id}').json()['items'][0]
    assert listing['completed'] == 7 and listing['recent_accuracy'] is None and listing['last_practiced_at'] is None
    session = client.post('/api/accumulation/sessions', json={'group_id': group.id}).json()
    question = session['current']
    choice = next(o for o in question['options'] if o != question['translation']) if wrong_choice else question['translation']
    session = action(client, session, 'choice', choice)
    if wrong_spell:
        session = action(client, session, 'spell', 'wrong')
        session = action(client, session, 'spell', 'wrong again')
    assert db.query(Log).count() == 0  # 未完成不算一次完整作答
    before = session
    session = action(client, session, 'spell', question['english'], 'complete-once')
    retried = action(client, before, 'spell', question['english'], 'complete-once')
    assert retried == session and session['completed'] == 1
    with factory() as reopened:
        log = reopened.query(Log).one()
        assert log.choice_correct == (not wrong_choice) and log.spelling_correct == (not wrong_spell)
        assert reopened.get(AccumulationEntry, item.id).completed == 8
    listing = client.get(f'/api/accumulation/entries?group_id={group.id}').json()['items'][0]
    assert listing['completed'] == 8 and listing['recent_attempts'] == 1
    assert listing['recent_accuracy'] == int(not wrong_choice and not wrong_spell)
    assert listing['last_practiced_at'].endswith('Z')
    session = action(client, session, 'next')
    assert session['finished']
    session = client.post('/api/accumulation/sessions', json={'group_id': group.id, 'restart': True}).json()
    assert db.query(Log).count() == 1
    session = action(client, session, 'choice', question['translation'])
    action(client, session, 'spell', question['english'])
    db.expire_all()
    assert db.query(Log).count() == 2 and item.completed == 9


def test_history_failure_rolls_back_completion_and_can_retry(client_db, monkeypatch):
    client, db, _ = client_db
    session = client.post('/api/accumulation/sessions', json={}).json()
    session = action(client, session, 'choice', session['current']['translation'])
    original = learning.record_completion
    def broken(*args):
        original(*args)
        raise RuntimeError('simulated write failure')
    with monkeypatch.context() as patch:
        patch.setattr(learning, 'record_completion', broken)
        with pytest.raises(RuntimeError):
            action(client, session, 'spell', session['current']['english'])
    assert client.get('/api/accumulation/sessions/current').json() == session
    db.expire_all()
    assert db.query(Log).count() == 0
    assert db.get(AccumulationEntry, session['current']['id']).completed == 0
    action(client, session, 'spell', session['current']['english'])
    assert db.query(Log).count() == 1


def test_history_deletion_is_scoped_and_classroom_has_no_stats(client_db):
    client, db, _ = client_db
    groups = []
    for index in range(2):
        group = AccumulationGroup(name=f'删除测试{index}')
        db.add(group)
        db.flush()
        for i in range(2):
            item = service.save_entry(db, {'group_id': group.id, 'item_type': 'word',
                'english': f'deleteword{index}{i}', 'translation': f'删除测试释义{index}{i}'},
                commit=False, library='accumulation')
            db.add(Log(entry_id=item.id, session_id=900, question_id=1000 + index * 10 + i,
                choice_correct=True, spelling_correct=True, completed_at=datetime(2026, 11, 5)))
        groups.append(group.id)
    db.commit()
    one = db.query(AccumulationEntry).filter_by(group_id=groups[0]).first()
    assert client.delete(f'/api/accumulation/entries/{one.id}').status_code == 200
    assert db.query(Log).count() == 3
    assert client.delete(f'/api/accumulation/groups/{groups[0]}').status_code == 200
    assert db.query(Log).count() == 2
    group = client.post('/api/classroom/groups', json={'name': '原课内流程'}).json()['id']
    for i in range(2):
        client.post('/api/classroom/entries', json={'group_id': group, 'item_type': 'word',
            'english': f'classroomword{i}', 'translation': f'课内释义{i}'})
    session = client.post('/api/classroom/sessions', json={'group_id': group}).json()
    q = session['current']
    from test_classroom import act
    # 共用服务仍仅为积累完成题记录新统计。
    session = act(db, session, 'choice', q['translation'])
    act(db, session, 'spell', q['english'])
    assert db.query(Log).count() == 2
    listed = client.get('/api/classroom/entries').json()['items']
    assert all('recent_accuracy' not in e and 'last_practiced_at' not in e for e in listed)


def test_upgrade_creates_only_new_history_table_and_preserves_existing_rows(client_db):
    from sqlalchemy import inspect, text
    from app.database import Base
    from scripts.seed import _migrate
    client, db, _ = client_db
    session = client.post('/api/accumulation/sessions', json={}).json()
    item = db.get(AccumulationEntry, session['current']['id'])
    item.completed, item.in_mistake_book, item.mistake_consec = 12, True, 2
    db.commit()
    saved_session = client.get('/api/accumulation/sessions/current').json()
    engine = db.get_bind()
    Log.__table__.drop(engine)
    tables = inspect(engine).get_table_names()
    before = {table: db.execute(text(f'SELECT * FROM "{table}" ORDER BY rowid')).all() for table in tables}
    db.commit()
    Base.metadata.create_all(engine)
    _migrate(db)
    Base.metadata.create_all(engine)
    _migrate(db)
    assert set(inspect(engine).get_table_names()) == set(tables) | {Log.__tablename__}
    assert db.query(Log).count() == 0
    for table in tables:
        assert db.execute(text(f'SELECT * FROM "{table}" ORDER BY rowid')).all() == before[table]
    listed = client.get(f'/api/accumulation/entries?search={item.english}').json()['items'][0]
    assert listed['completed'] == 12 and listed['mistake_consec'] == 2
    assert listed['recent_accuracy'] is None and listed['last_practiced_at'] is None
    assert client.get('/api/accumulation/sessions/current').json() == saved_session


def test_missing_phonetic_in_old_accumulation_snapshot_backfills_without_reselection(client_db):
    import json
    client, db, _ = client_db
    group = AccumulationGroup(name='旧轮次音标')
    db.add(group)
    db.flush()
    service.save_entry(db, {'group_id': group.id, 'item_type': 'word',
        'english': 'benefaction', 'translation': 'n. 捐赠'}, commit=False, library='accumulation')
    db.commit()
    session = client.post('/api/accumulation/sessions', json={'group_id': group.id}).json()
    session = action(client, session, 'choice', session['current']['translation'])
    question = db.get(AccumulationSessionItem, session['current']['question_id'])
    old = json.loads(question.snapshot)
    old['phonetic_us'] = ''
    question.snapshot = json.dumps(old)
    db.commit()
    restored = client.get(f'/api/accumulation/sessions/current?group_id={group.id}').json()
    assert restored == session
    assert restored['current']['phonetic_us'] == 'ˌben.əˈfæk.ʃən'
    assert restored['current']['stage'] == 'spell'
