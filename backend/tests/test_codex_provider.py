"""Codex 连接、隔离、超时及错误处理。"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import Base, get_db
from app.models import AiProvider, Submission, Grading
from app.routers import practice, settings
from app.services import ai_client, codex_provider, grading


def test_login_requires_chatgpt_and_masks_output(monkeypatch):
    monkeypatch.setattr(codex_provider, '_executable', lambda: 'codex')
    monkeypatch.setattr(codex_provider.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='Logged in using an API key: secret', stderr=''))
    ok, message = codex_provider.login_status()
    assert not ok and 'ChatGPT' in message and 'secret' not in message
    monkeypatch.setattr(codex_provider.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='Logged in using ChatGPT', stderr=''))
    assert codex_provider.login_status()[0]


def test_codex_call_stdin_isolated_and_no_key_fallback(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'private-key')
    monkeypatch.setattr(codex_provider, '_executable', lambda: 'codex')
    monkeypatch.setattr(codex_provider, 'login_status', lambda **kwargs: (True, 'ok'))
    monkeypatch.setattr(codex_provider, '_default_model', lambda: 'example-model')
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"score": 13}', stderr='')
    monkeypatch.setattr(codex_provider.subprocess, 'run', run)
    assert ai_client.chat({'service_type':'codex'}, [{'role':'user', 'content':'private answer'}]) == '{"score": 13}'
    command, kwargs = calls[0]
    assert 'private answer' in kwargs['input'] and 'private answer' not in str(command)
    assert 'OPENAI_API_KEY' not in kwargs['env'] and '--ignore-user-config' in command
    assert 'read-only' in command and '--ephemeral' in command and 'shell_tool' in command
    assert '--model' in command and command[command.index('--model') + 1] == 'example-model'
    assert not Path(kwargs['cwd']).exists()


@pytest.mark.parametrize('error,expected', [
    ('HTTP 429 secret', '额度'), ('401 secret', '认证'), ('403 secret', '权限'), ('model_not_found secret', '模型'), ('other secret', '失败')
])
def test_error_messages_are_safe(monkeypatch, error, expected):
    monkeypatch.setattr(codex_provider, '_executable', lambda: 'codex')
    monkeypatch.setattr(codex_provider, 'login_status', lambda **kwargs: (True, 'ok'))
    monkeypatch.setattr(codex_provider, '_default_model', lambda: '')
    monkeypatch.setattr(codex_provider.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1, stdout='', stderr=error))
    with pytest.raises(ai_client.AiError) as exc:
        codex_provider.complete([{'role':'user', 'content':'test'}])
    assert expected in str(exc.value) and 'secret' not in str(exc.value)


def test_timeout_and_invalid_results_are_rejected(monkeypatch):
    monkeypatch.setattr(codex_provider, '_executable', lambda: 'codex')
    monkeypatch.setattr(codex_provider, 'login_status', lambda **kwargs: (True, 'ok'))
    monkeypatch.setattr(codex_provider, '_default_model', lambda: '')
    def timeout(*args, **kwargs): raise subprocess.TimeoutExpired('codex', 1)
    monkeypatch.setattr(codex_provider.subprocess, 'run', timeout)
    with pytest.raises(ai_client.AiError, match='3 分钟'):
        codex_provider.complete([{'role':'user', 'content':'test'}])
    monkeypatch.setattr(ai_client, 'chat', lambda *a, **kw: json.dumps({'score': 12, 'overall_comment': 'ok'}))
    with pytest.raises(ai_client.AiError, match='不完整'):
        grading.grade('ky2', 'translation', '', 'source', 'answer', 1, {'service_type':'codex'})


def test_codex_setting_and_practice_preserve_existing_default(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(AiProvider(name='old', base_url='https://example.invalid', api_key='test', model='x', is_default=True))
        db.commit()
    app = FastAPI(); app.include_router(settings.router)
    def get_test_db():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = get_test_db
    monkeypatch.setattr(codex_provider, 'login_status', lambda: (True, '登录成功'))
    with TestClient(app) as api:
        assert api.get('/api/settings/codex/status').json()['ok']
        created = api.post('/api/settings/providers/codex').json()
        assert created['service_type'] == 'codex' and not created['is_default'] and not created['api_key_masked']
        assert api.post('/api/settings/providers/codex').json()['id'] == created['id']
        assert api.get('/api/settings').json()['providers'][0]['is_default']
    monkeypatch.setattr(practice, 'SessionLocal', factory)
    monkeypatch.setattr(practice, 'grade', lambda *args: {'score': 12, 'overall_comment': 'ok'})
    with factory() as db:
        sub = Submission(exam_type='cet6', q_type='translation', content='answer', word_count=1)
        db.add(sub); db.commit(); sid = sub.id
    practice._run_grading(sid, created['id'])
    with factory() as db:
        assert db.get(Submission, sid).status == 'done'
        result = db.query(Grading).filter_by(submission_id=sid).one()
        assert not result.mock and result.provider == created['name'] and result.model == 'Codex 默认模型'
    engine.dispose()


def test_practice_failure_preserves_answer_without_simulation(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'failure.db'}", connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        provider = AiProvider(name='Codex', base_url='', api_key='', model='', service_type='codex', is_default=True)
        sub = Submission(exam_type='cet6', q_type='translation', content='saved answer', word_count=2)
        db.add_all([provider, sub]); db.commit(); sid, pid = sub.id, provider.id
    monkeypatch.setattr(practice, 'SessionLocal', factory)
    def fail(*args): raise ai_client.AiError('Codex 额度不足')
    monkeypatch.setattr(practice, 'grade', fail)
    practice._run_grading(sid, pid)
    with factory() as db:
        saved = db.get(Submission, sid)
        assert saved.status == 'failed' and saved.content == 'saved answer'
        result = db.query(Grading).filter_by(submission_id=sid).one()
        assert not result.mock and '额度' in result.error
    engine.dispose()


def test_catalogue_filters_hidden_and_exposes_supported_effort_only(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    (tmp_path / 'models_cache.json').write_text(json.dumps({
        'identity': {'token': 'never-expose'},
        'models': [
            {'slug':'good-model', 'display_name':'Good', 'visibility':'list',
             'supported_reasoning_levels':[{'effort':'low'}, {'effort':'high'}, {'effort':'bad'}]},
            {'slug':'hidden', 'visibility':'hide'}, {'slug':'bad;command', 'visibility':'list'},
        ]}), encoding='utf-8')
    (tmp_path / 'config.toml').write_text('model = "good-model"', encoding='utf-8')
    assert codex_provider.model_catalogue() == [{'id':'good-model', 'name':'Good', 'levels':['low', 'high']}]
    codex_provider.validate_selection('', 'high')
    with pytest.raises(ValueError, match='不支持'): codex_provider.validate_selection('good-model', 'medium')
    with pytest.raises(ValueError, match='模型名'): codex_provider.validate_selection('bad;command', '')
    with pytest.raises(ValueError, match='强度'): codex_provider.validate_selection('good-model', 'invalid')


def test_selected_model_and_effort_reach_codex_cli(monkeypatch):
    monkeypatch.setattr(codex_provider, '_executable', lambda: 'codex')
    monkeypatch.setattr(codex_provider, 'login_status', lambda **kwargs: (True, 'ok'))
    monkeypatch.setattr(codex_provider, 'model_catalogue', lambda: [{'id':'test-model', 'name':'Test', 'levels':['low','high']}])
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='ok', stderr='')
    monkeypatch.setattr(codex_provider.subprocess, 'run', run)
    assert ai_client.chat({'service_type':'codex', 'model':'test-model', 'reasoning_effort':'high'}, [{'role':'user','content':'sample'}]) == 'ok'
    assert calls[0][calls[0].index('--model') + 1] == 'test-model'
    assert 'model_reasoning_effort="high"' in calls[0]
    assert '--ignore-user-config' in calls[0] and 'read-only' in calls[0]


def test_codex_settings_round_trip_preserves_provider_and_default(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_provider, 'model_catalogue', lambda: [{'id':'test-model', 'name':'Test', 'levels':['low','high']}])
    monkeypatch.setattr(codex_provider, '_default_model', lambda: 'test-model')
    engine = create_engine(f"sqlite:///{tmp_path / 'settings.db'}", connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine); factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(AiProvider(name='Codex', base_url='', api_key='', model='', service_type='codex', is_default=True))
        db.add(AiProvider(name='Other', base_url='https://example.invalid', api_key='secret', model='other', is_default=False))
        db.commit()
    app = FastAPI(); app.include_router(settings.router)
    def get_test_db():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = get_test_db
    with TestClient(app) as api:
        models = api.get('/api/settings/codex/models').json()
        assert models['default_model'] == 'test-model' and models['models'][0]['levels'] == ['low','high']
        saved = api.put('/api/settings/providers/1/codex', json={'model':'test-model','reasoning_effort':'high'})
        assert saved.status_code == 200 and saved.json()['model'] == 'test-model' and saved.json()['reasoning_effort'] == 'high'
        assert saved.json()['is_default'] and not saved.json()['api_key_masked']
        assert api.put('/api/settings/providers/1/codex', json={'model':'test-model','reasoning_effort':'medium'}).status_code == 400
        assert api.put('/api/settings/providers/2/codex', json={'model':'test-model','reasoning_effort':'high'}).status_code == 404
        restored = api.put('/api/settings/providers/1/codex', json={'model':'','reasoning_effort':''}).json()
        assert restored['model'] == restored['reasoning_effort'] == '' and restored['is_default']
        with factory() as db: assert db.get(AiProvider, 2).api_key == 'secret'
    engine.dispose()


def test_missing_catalogue_allows_valid_manual_model_without_modifying_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    assert codex_provider.model_catalogue() == []
    codex_provider.validate_selection('future-model', 'medium')
    codex_provider.validate_selection('', '')
