"""Claude 官方与 Go 的协议、参数、目录及设置回归，全部使用模拟传输。"""
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import Base, get_db
from app.models import AiProvider
from app.routers.settings import router
from app.services import ai_client as client, ai_profiles as profiles


def provider(**patch):
    return {'service_type': 'anthropic', 'base_url': 'https://api.anthropic.com', 'model': 'claude-haiku-5-5',
            'api_key': 'fake-native-key', 'reasoning_mode': 'enabled', 'reasoning_effort': 'high', **patch}


def response(text='{"score":13}', reason='end_turn'):
    return httpx.Response(200, json={'type': 'message', 'stop_reason': reason,
        'content': [{'type': 'thinking', 'thinking': 'not the grade'}, {'type': 'text', 'text': text}]})


@pytest.fixture
def wire(monkeypatch):
    calls, replies = [], []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def _send(self, method, url, **kwargs):
            calls.append({'method': method, 'url': url, **json.loads(json.dumps(kwargs))})
            value = replies.pop(0)
            if isinstance(value, Exception): raise value
            return value
        def post(self, url, **kwargs): return self._send('post', url, **kwargs)
        def get(self, url, **kwargs): return self._send('get', url, **kwargs)
    monkeypatch.setattr(httpx, 'Client', Client)
    return calls, replies


@pytest.mark.parametrize('base', ['https://api.anthropic.com', 'https://api.anthropic.com/v1/', 'https://api.anthropic.com/v1/messages'])
def test_official_url_headers_payload_and_body_only(wire, base):
    calls, replies = wire; replies.append(response())
    result = client.chat(provider(base_url=base), [{'role': 'system', 'content': 'Teacher instructions'},
        {'role': 'user', 'content': 'My answer'}], max_tokens=8000)
    assert json.loads(result) == {'score': 13}
    call = calls[0]
    assert call['url'] == 'https://api.anthropic.com/v1/messages'
    assert call['headers']['Authorization'] == 'Bearer fake-native-key'
    assert call['headers']['anthropic-version'] == '2026-10-21'
    assert 'x-opencode-session' not in call['headers']
    body = call['json']
    assert body['system'] == 'Teacher instructions' and body['messages'] == [{'role': 'user', 'content': 'My answer'}]
    assert body['thinking'] == {'type': 'adaptive'} and body['output_config'] == {'effort': 'high'}
    assert not {'temperature', 'reasoning_effort', 'top_p'} & body.keys()


@pytest.mark.parametrize('base', ['https://opencode.ai/zen/go/v1', 'https://opencode.ai/inference/go/openai/v1',
                                  'https://opencode.ai/inference/go/anthropic/v1/messages'])
def test_existing_go_claude_auto_routes_and_retry_keeps_session(wire, base):
    calls, replies = wire; replies.extend([response('{', 'max_tokens'), response()])
    p = provider(service_type='opencode_go', base_url=base, reasoning_effort='max', session_id='persisted-short-run')
    assert profiles.capabilities(p)['levels'] == ['low', 'medium', 'high', 'xhigh', 'max']
    client.chat(p, [{'role': 'user', 'content': 'Translate'}], max_tokens=8000)
    assert [c['json']['max_tokens'] for c in calls] == [8000, 16000]
    for call in calls:
        assert call['url'] == 'https://opencode.ai/inference/go/anthropic/v1/messages'
        assert call['headers']['x-opencode-session'] == 'persisted-short-run'
        assert call['headers']['User-Agent'] == 'EnglishLearningPlatform/1.0'
        assert call['headers']['Authorization'] == 'Bearer fake-native-key'
        assert call['json']['output_config'] == {'effort': 'max'}


def test_go_native_url_switches_back_for_chat_model():
    p = provider(service_type='opencode_go', base_url='https://opencode.ai/inference/go/anthropic/v1', model='glm-5.3-flash')
    assert client.request_url(p) == 'https://opencode.ai/inference/go/openai/v1/chat/completions'
    proxy = provider(service_type='custom', base_url='https://example.invalid/v1')
    assert profiles.api_format(proxy) == 'chat-completions'


def test_off_omits_effort_and_legacy_budget_and_forced_models():
    assert client._extra_payload(provider(reasoning_mode='disabled', reasoning_effort='max')) == {'thinking': {'type': 'disabled'}}
    assert client._extra_payload(provider(reasoning_mode='auto', reasoning_effort='')) == {}
    p = provider(model='claude-haiku-4-5-20251001', reasoning_effort='')
    extra = client._extra_payload(p)
    assert extra == {'thinking': {'type': 'enabled', 'budget_tokens': 4096}}
    payload = client.messages_payload(p, [{'role': 'user', 'content': 'a'}], 256, extra, {})
    assert payload['max_tokens'] > payload['thinking']['budget_tokens']
    for model in ('claude-opus-5-5', 'claude-sonnet-5-5'):
        with pytest.raises(ValueError): profiles.validate(provider(model=model, reasoning_mode='disabled'))
    unknown = provider(model='future-claude', reasoning_mode='auto', reasoning_effort='')
    assert profiles.capabilities(unknown)['modes'] == ['auto']
    assert client._extra_payload(unknown) == {}


def test_connection_uses_native_body_and_same_configuration(wire):
    calls, replies = wire; replies.append(response('OK'))
    ok, _ = client.test_connection(provider(reasoning_effort='xhigh'))
    assert ok and calls[0]['json']['output_config']['effort'] == 'xhigh'
    assert calls[0]['json']['max_tokens'] >= 8000


@pytest.mark.parametrize('payload', [None, {'content': None, 'stop_reason': 'end_turn'},
    {'content': [{'type': 'text', 'text': 3}], 'stop_reason': 'end_turn'},
    {'content': [{'type': 'thinking', 'thinking': 'only thinking'}], 'stop_reason': 'end_turn'},
    {'content': [{'type': 'text', 'text': '{"score":15}'}], 'stop_reason': 'tool_use'},
    {'content': [], 'stop_reason': 'refusal'}])
def test_bad_or_incomplete_responses_never_become_grades(wire, payload):
    calls, replies = wire; replies.append(httpx.Response(200, json=payload))
    with pytest.raises(client.AiError): client.chat(provider(), [{'role': 'user', 'content': 'a'}])
    assert len(calls) == 1


def test_output_limit_and_timeout_remain_explicit_errors(wire):
    calls, replies = wire; replies.append(response('{', 'max_tokens'))
    with pytest.raises(client.AiError, match='长度上限'):
        client.chat(provider(), [{'role': 'user', 'content': 'a'}], max_tokens=65536)
    replies.append(httpx.ReadTimeout('fake timeout'))
    with pytest.raises(client.AiError, match='超时'): client.chat(provider(), [{'role': 'user', 'content': 'a'}])


def test_go_refresh_keeps_messages_models_and_declared_effort(wire):
    _, replies = wire; replies.append(httpx.Response(200, json={'data': [
        {'id': 'claude-haiku-5-5', 'api': {'messages': {}}, 'api_key': 'must-not-store',
         'capabilities': {'reasoning': {'effort': ['low', 'medium', 'high', 'xhigh', 'max']}}},
        {'id': 'other-messages-model', 'api': {'messages': {}}, 'capabilities': {'reasoning': {'effort': ['low', 'high']}}},
        {'id': 'responses-only', 'api': {'responses': {}}}] }))
    p = provider(service_type='opencode_go', base_url='https://opencode.ai/inference/go/openai/v1')
    models = client.refresh_models(p)
    assert len(models) == 2 and models[0]['api_format'] == 'messages' and 'api_key' not in models[0]
    p.update(model='other-messages-model', models_json=json.dumps(models), reasoning_mode='auto', reasoning_effort='low')
    assert client._extra_payload(p) == {'output_config': {'effort': 'low'}}


def test_official_model_pagination_and_declared_capabilities(wire):
    calls, replies = wire
    item = {'id': 'new-claude', 'display_name': 'New Claude', 'capabilities': {
        'thinking': {'types': {'adaptive': {'supported': True}, 'disabled': {'supported': False}}},
        'effort': {'supported': True, 'low': {'supported': True}, 'high': {'supported': True}}}}
    replies.extend([httpx.Response(200, json={'data': [item], 'has_more': True, 'last_id': 'new-claude'}),
                    httpx.Response(200, json={'data': [{'id': 'second-claude'}], 'has_more': False})])
    models = client.refresh_models(provider())
    assert len(models) == 2 and 'after_id=new-claude' in calls[1]['url']
    p = provider(model='new-claude', models_json=json.dumps(models))
    caps = profiles.capabilities(p)
    assert caps['modes'] == ['auto', 'enabled'] and caps['levels'] == ['low', 'high']
    assert client._extra_payload(p) == {'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'high'}}


def test_official_entry_cannot_send_go_key_to_wrong_host():
    with pytest.raises(ValueError): profiles.validate(provider(base_url='https://opencode.ai/inference/go/anthropic/v1'))


def test_metadata_can_limit_model_to_off_and_no_effort():
    cache = [{'id': 'new-nonthinking-claude', 'thinking': {'adaptive': False, 'enabled': False, 'disabled': True},
              'effort': {'supported_levels': []}}]
    p = provider(model='new-nonthinking-claude', models_json=json.dumps(cache), reasoning_mode='disabled', reasoning_effort='')
    assert profiles.capabilities(p)['modes'] == ['auto', 'disabled']
    assert client._extra_payload(p) == {'thinking': {'type': 'disabled'}}


def test_bad_models_pagination_rejects_partial_refresh(wire):
    _, replies = wire
    page = {'data': [{'id': 'claude-haiku-5-5'}], 'has_more': True, 'last_id': 'same-id'}
    replies.extend([httpx.Response(200, json=page), httpx.Response(200, json=page)])
    with pytest.raises(client.AiError, match='已保留原配置'): client.refresh_models(provider())


def test_settings_native_profile_key_mask_and_existing_go_capability(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'native.db'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine); factory = sessionmaker(bind=engine)
    app = FastAPI(); app.include_router(router)
    def connection():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = connection
    with TestClient(app) as api:
        payload = {**provider(), 'name': 'Anthropic 官方'}
        saved = api.post('/api/settings/providers', json=payload)
        assert saved.status_code == 200, saved.text
        data = saved.json(); pid = data['id']
        assert 'fake-native-key' not in saved.text and data['reasoning_effort'] == 'high'
        updated = api.put(f'/api/settings/providers/{pid}', json={**payload, 'api_key': data['api_key_masked'], 'reasoning_mode': 'disabled'})
        assert updated.status_code == 200 and updated.json()['reasoning_effort'] == ''
        with factory() as db: assert db.get(AiProvider, pid).api_key == 'fake-native-key'
        opts = api.get('/api/settings/provider-options').json()['profiles']
        assert any(p['service_type'] == 'anthropic' for p in opts)
        caps = api.post('/api/settings/provider-capabilities', json={'service_type': 'opencode_go',
            'base_url': 'https://opencode.ai/inference/go/openai/v1', 'model': 'claude-haiku-5-5'}).json()
        assert caps['modes'] == ['auto', 'enabled', 'disabled'] and len(caps['levels']) == 5
    engine.dispose()
