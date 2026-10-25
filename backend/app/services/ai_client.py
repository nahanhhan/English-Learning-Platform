"""OpenAI 兼容服务调用。依据保留的接口、测试与规格重建。"""
import json
import re

import httpx


class AiError(Exception):
    pass


def build_url(base_url: str) -> str:
    url = base_url.strip().rstrip('/')
    if url.endswith('/chat/completions'):
        return url
    if not re.search(r'/v\d+(?:[a-z][\w.-]*)?$', url, re.I):
        url += '/v1'
    return url + '/chat/completions'


def _extra_payload(provider: dict) -> dict:
    model = provider.get('model', '').lower()
    if model.startswith('glm-4'):
        return {'thinking': {'type': 'disabled'}}
    return {}


def extract_json(text: str) -> dict:
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', text):
        try:
            result, _ = decoder.raw_decode(text[match.start():])
        except ValueError:
            continue
        if isinstance(result, dict):
            return result
    raise AiError('AI 返回的内容不是有效的 JSON 对象，请重试批改')


def chat(provider: dict, messages: list, max_tokens: int = 8000,
         temperature: float = 0.3, **kwargs) -> str:
    payload = {'model': provider.get('model', ''), 'messages': messages,
               'max_tokens': min(65536, max(1, int(max_tokens))), 'temperature': temperature,
               **_extra_payload(provider), **kwargs}
    headers = {'Authorization': 'Bearer ' + provider.get('api_key', ''),
               'Content-Type': 'application/json'}
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=30)) as client:
            while True:
                response = client.post(build_url(provider['base_url']), json=payload, headers=headers)
                if response.status_code >= 400:
                    # 错误文本不附带密钥或请求头。
                    raise AiError(f'AI 服务返回 HTTP {response.status_code}，请检查模型、地址、密钥与额度')
                try:
                    choice = response.json()['choices'][0]
                    message = choice['message']
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise AiError('AI 服务返回了无法识别的响应') from exc
                content = message.get('content') or ''
                if isinstance(content, list):
                    content = ''.join(part.get('text', '') for part in content if isinstance(part, dict))
                # 思考耗尽配额时重试；截断的非空 JSON 同样不能直接用于评分。
                if choice.get('finish_reason') == 'length':
                    if payload['max_tokens'] < 65536:
                        payload['max_tokens'] = min(65536, payload['max_tokens'] * 2)
                        continue
                    raise AiError('AI 输出达到长度上限，请换用更合适的模型或缩短作答后重试')
                if not isinstance(content, str) or not content.strip():
                    raise AiError('AI 返回正文为空，请检查模型或重试')
                return content.strip()
    except httpx.TimeoutException as exc:
        raise AiError('AI 请求超时，请稍后重试') from exc
    except httpx.RequestError as exc:
        raise AiError('无法连接 AI 服务，请检查地址和网络') from exc


def test_connection(provider: dict) -> tuple[bool, str]:
    try:
        reply = chat(provider, [{'role': 'user', 'content': 'Reply with OK.'}],
                     max_tokens=32000 if provider.get('model', '').lower().startswith('glm-5') else 256)
        return True, '连接成功：' + reply[:120]
    except AiError as exc:
        return False, str(exc)
