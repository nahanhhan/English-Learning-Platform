"""推理参数、Go 会话请求头、模型刷新和旧配置迁移。"""
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import Base, get_db
from app.models import AiProvider
from app.services import ai_client as client, ai_profiles as profiles
from app.routers.settings import router
from scripts.seed import _migrate


def go(**patch):
    return {'service_type': 'opencode_go', 'base_url': 'https://opencode.ai/inference/go/openai/v1',
            'model': 'deepseek-v4-pro', 'api_key': 'test-secret-not-real',
            'reasoning_mode': 'enabled', 'reasoning_effort': 'high', **patch}


def complete(content='{"ok":true}', reason='stop'):
    return httpx.Response(200, json={'choices': [{'finish_reason': reason, 'message': {'content': content}}]})


def transport(monkeypatch, responses):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json, headers):
            calls.append({'url': url, 'body': dict(json), 'headers': dict(headers)})
            value = responses.pop(0)
            if isinstance(value, Exception): raise value
            return value
        def get(self, url, headers):
            calls.append({'url': url, 'headers': dict(headers)})
            value = responses.pop(0)
            if isinstance(value, Exception): raise value
            return value
    monkeypatch.setattr(httpx, 'Client', Client)
    return calls


def test_deepseek_effort_controls_and_off_omits_effort():
    provider = go(service_type='deepseek', base_url='https://api.deepseek.com', model='deepseek-flash')
    assert profiles.capabilities(provider)['levels'] == ['low', 'high', 'max']
    assert client._extra_payload(provider) == {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'}
    provider['reasoning_mode'] = 'disabled'
    assert client._extra_payload(provider) == {'thinking': {'type': 'disabled'}}
    provider['reasoning_mode'] = 'enabled'; provider['reasoning_effort'] = 'medium'
    with pytest.raises(ValueError): profiles.validate(provider)


def test_always_reasoning_and_unknown_model_are_not_guessed():
    provider = go(model='glm-5.3-flash', reasoning_mode='auto', reasoning_effort='')
    assert 'disabled' not in profiles.capabilities(provider)['modes']
    assert profiles.capabilities(provider)['levels'] == ['low', 'high', 'max']
    provider['reasoning_mode'] = 'disabled'
    with pytest.raises(ValueError): profiles.validate(provider)
    custom = {'model': 'brand-new-model', 'base_url': 'https://example.invalid/v1', 'service_type': 'custom', 'reasoning_mode': 'auto'}
    assert client._extra_payload(custom) == {}
    custom['reasoning_mode'] = 'enabled'
    with pytest.raises(ValueError): profiles.validate(custom)


@pytest.mark.parametrize('base', ['https://opencode.ai/zen/go/v1', 'https://opencode.ai/inference/go/openai/v1'])
def test_go_headers_identify_client_and_stay_stable_across_output_retries(monkeypatch, base):
    calls = transport(monkeypatch, [complete('', 'length'), complete()])
    provider = go(base_url=base)
    reply = client.chat(provider, [{'role': 'user', 'content': 'sample'}], max_tokens=8000, session_id='short-stable-run')
    assert reply == '{"ok":true}' and len(calls) == 2
    for call in calls:
        assert call['url'] == base + '/chat/completions'
        assert call['headers']['x-opencode-session'] == 'short-stable-run'
        assert call['headers']['User-Agent'] == 'EnglishLearningPlatform/1.0'
        assert call['headers']['Authorization'] == 'Bearer test-secret-not-real'
        assert 'session_id' not in call['body'] and 'temperature' not in call['body']
        assert call['body']['reasoning_effort'] == 'high'
    assert [c['body']['max_tokens'] for c in calls] == [8000, 16000]


def test_new_calls_get_distinct_session_ids_and_other_services_do_not_receive_go_headers(monkeypatch):
    calls = transport(monkeypatch, [complete(), complete(), complete()])
    client.chat(go(), [])
    client.chat(go(), [])
    client.chat({'base_url': 'https://api.deepseek.com', 'model': 'deepseek-chat', 'api_key': 'fake'}, [])
    assert calls[0]['headers']['x-opencode-session'] != calls[1]['headers']['x-opencode-session']
    assert 'x-opencode-session' not in calls[2]['headers'] and 'User-Agent' not in calls[2]['headers']


def test_connection_test_uses_same_headers_and_reasoning_configuration(monkeypatch):
    calls = transport(monkeypatch, [complete('OK')])
    ok, message = client.test_connection(go(session_id='connection-session'))
    assert ok and '连接成功' in message
    assert calls[0]['headers']['x-opencode-session'] == 'connection-session'
    assert calls[0]['body']['thinking'] == {'type': 'enabled'}
    assert calls[0]['body']['reasoning_effort'] == 'high'
    assert calls[0]['body']['max_tokens'] >= 8000


@pytest.mark.parametrize('code,payload,expected', [
    (400, {'error': {'type': 'MissingSessionID', 'message': 'test-secret-not-real'}}, '会话请求头'),
    (401, {}, '认证失败'), (403, {}, '权限'), (402, {}, '额度'), (429, {}, '额度'),
    (400, {}, '参数'), (500, {}, '不会自动切换'),
])
def test_errors_are_specific_and_do_not_leak_secrets(monkeypatch, code, payload, expected):
    calls = transport(monkeypatch, [httpx.Response(code, json=payload)])
    with pytest.raises(client.AiError) as err: client.chat(go(), [])
    assert expected in str(err.value) and 'test-secret-not-real' not in str(err.value)
    assert len(calls) == 1


def test_model_metadata_only_enables_declared_levels(monkeypatch):
    calls = transport(monkeypatch, [httpx.Response(200, json={'data': [
        {'id': 'new-go-model', 'name': 'New model', 'capabilities': {'reasoning': {'effort': ['low', 'high']}},
         'api': {'chat-completions': {}}, 'api_key': 'never-store'},
        {'id': 'responses-only', 'api': {'responses': {}}},
    ]})])
    models = client.refresh_models(go())
    assert calls[0]['url'] == 'https://opencode.ai/inference/go/v1/models'
    assert len(models) == 1
    assert 'x-opencode-session' in calls[0]['headers']
    assert 'api_key' not in models[0]
    provider = go(model='new-go-model', models_json=json.dumps(models), reasoning_mode='auto', reasoning_effort='low')
    assert profiles.capabilities(provider)['levels'] == ['low', 'high']
    assert client._extra_payload(provider) == {'reasoning_effort': 'low'}


def test_go_cannot_use_paid_or_other_host_as_subscription():
    for url in ('https://opencode.ai/inference/openai/v1', 'https://not-opencode.example/v1', 'http://opencode.ai/zen/go/v1'):
        with pytest.raises(ValueError): profiles.validate(go(base_url=url))


@pytest.mark.parametrize('message', [None, {'content': [{'text': None}]}])
def test_malformed_response_message_is_classified(monkeypatch, message):
    transport(monkeypatch, [httpx.Response(200, json={'choices': [{'message': message}]})])
    with pytest.raises(client.AiError, match='格式错误'): client.chat(go(), [])


def test_old_provider_schema_migration_preserves_values_and_glm4_behavior(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.execute(text('CREATE TABLE ai_providers (id INTEGER PRIMARY KEY, name TEXT, base_url TEXT, api_key TEXT, model TEXT, is_default BOOLEAN)'))
        db.execute(text("INSERT INTO ai_providers VALUES (8,'原配置','https://open.bigmodel.cn/api/paas/v4','fake-old-key','glm-4.6',1)"))
        db.commit()
        _migrate(db); _migrate(db)
        provider = db.get(AiProvider, 8)
        assert provider.name == '原配置' and provider.api_key == 'fake-old-key' and provider.is_default
        assert provider.reasoning_mode == 'disabled' and provider.reasoning_effort == ''
        assert client._extra_payload(profiles.config(provider)) == {'thinking': {'type': 'disabled'}}
    engine.dispose()


def test_settings_round_trip_capabilities_masked_key_and_refresh_failure(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI(); app.include_router(router)
    def connection():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = connection
    with TestClient(app) as api:
        body = {'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash',
                'api_key': 'secret-key-test-123456', 'service_type': 'deepseek', 'reasoning_mode': 'enabled', 'reasoning_effort': 'max'}
        response = api.post('/api/settings/providers', json=body)
        assert response.status_code == 200, response.text
        profile = response.json()
        assert profile['reasoning_effort'] == 'max' and profile['capabilities']['levels'] == ['low', 'high', 'max']
        assert 'api_key' not in profile and '****' in profile['api_key_masked']
        saved = api.put(f"/api/settings/providers/{profile['id']}", json={**body, 'api_key': profile['api_key_masked'], 'reasoning_mode': 'disabled'})
        assert saved.status_code == 200 and saved.json()['reasoning_effort'] == ''
        with factory() as db: assert db.get(AiProvider, profile['id']).api_key == body['api_key']
        monkeypatch.setattr(client, 'refresh_models', lambda provider: (_ for _ in ()).throw(client.AiError('网络不可用，原配置保留')))
        assert api.post(f"/api/settings/providers/{profile['id']}/models").status_code == 400
        reloaded = api.get('/api/settings').json()['providers'][0]
        assert reloaded['model'] == 'deepseek-flash' and reloaded['reasoning_mode'] == 'disabled'
        caps = api.post('/api/settings/provider-capabilities', json={'service_type': 'opencode_go', 'base_url': 'https://opencode.ai/zen/go/v1', 'model': 'glm-5.3-flash'}).json()
        assert caps['modes'] == ['auto', 'enabled']
        assert len(api.get('/api/settings/provider-options').json()['presets']) >= 3
    engine.dispose()
