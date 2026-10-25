"""重建模块的故障处理验证；不连接真实 AI 服务。"""
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import ai_client, grading


def provider():
    return {'base_url': 'https://example.invalid/v1', 'model': 'glm-5.3', 'api_key': 'test-only'}


def install_client(monkeypatch, responses):
    requests = []
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json, headers):
            requests.append(dict(json))
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
    monkeypatch.setattr(ai_client.httpx, 'Client', Client)
    return requests


def completion(content, reason='stop'):
    return httpx.Response(200, json={'choices': [{'finish_reason': reason,
                         'message': {'content': content, 'reasoning_content': 'thinking'}}]})


def test_reasoning_exhaustion_retries_and_never_disables_glm5(monkeypatch):
    requests = install_client(monkeypatch, [completion('', 'length'), completion('{"score":12}')])
    assert ai_client.chat(provider(), [], max_tokens=32000) == '{"score":12}'
    assert [request['max_tokens'] for request in requests] == [32000, 64000]
    assert all('thinking' not in request for request in requests)


def test_truncated_json_at_limit_is_rejected(monkeypatch):
    install_client(monkeypatch, [completion('{"score":', 'length')])
    with pytest.raises(ai_client.AiError, match='长度上限'):
        ai_client.chat(provider(), [], max_tokens=65536)


@pytest.mark.parametrize('response,detail', [
    (httpx.Response(401), 'HTTP 401'),
    (httpx.Response(200, json={}), '无法识别'),
    (httpx.ConnectError('connection failed'), '无法连接'),
])
def test_provider_errors_are_useful_without_exposing_key(monkeypatch, response, detail):
    install_client(monkeypatch, [response])
    with pytest.raises(ai_client.AiError, match=detail) as error:
        ai_client.chat(provider(), [])
    assert provider()['api_key'] not in str(error.value)


def test_nonfinite_scores_and_malformed_dimensions_are_safe():
    result = grading._validate({'score': 'NaN', 'dimensions': [], 'errors': None}, 'translation')
    assert result['score'] == 0
    assert result['dimensions'] == {'accuracy': 0, 'language': 0, 'fluency': 0}
    assert result['errors'] == []


def test_nested_feedback_is_safe_to_render():
    result = grading._validate({'errors': [None, 'text', {'explanation': '说明'}],
                                'good_points': [None, '亮点'],
                                'key_notes': [None, {'expr': 'word'}]}, 'translation')
    assert len(result['errors']) == 1
    assert result['errors'][0]['fragment'] == ''
    assert result['good_points'] == ['亮点']
    assert result['key_notes'] == [{'expr': 'word', 'note': ''}]
