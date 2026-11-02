"""OpenAI 兼容服务调用。依据保留的接口、测试与规格重建。"""
import json
import re
import uuid

import httpx
from . import ai_profiles


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
    return ai_profiles.reasoning_payload(provider)


def request_headers(provider: dict, session_id: str) -> dict:
    headers = {'Authorization': 'Bearer ' + provider.get('api_key', ''), 'Content-Type': 'application/json'}
    if ai_profiles.service_type(provider) == 'opencode_go':
        headers.update({'User-Agent': 'EnglishLearningPlatform/1.0', 'x-opencode-session': session_id})
    return headers


def response_error(response) -> str:
    # 只利用响应内容分类，绝不把供应商原始响应或密钥直接展示到界面。
    try:
        detail = json.dumps(response.json(), ensure_ascii=False).lower()
    except (ValueError, TypeError):
        detail = ''
    code = response.status_code
    prefix = f'AI 服务返回 HTTP {code}：'
    if 'missingsession' in detail or 'x-opencode-session' in detail:
        return prefix + 'Go 会话请求头未被接受，请检查连接测试及订阅接口'
    if code == 401:
        return prefix + '认证失败，请检查密钥是否有效或已过期'
    if code == 403:
        return prefix + '没有模型访问权限，或该服务不支持当前用途，请核对账户权限及适用范围'
    if code in (402, 429):
        return prefix + '额度不足或请求过于频繁，请检查订阅额度、余额或稍后重试'
    if code == 400:
        return prefix + '请求参数不被模型支持，请检查模型、推理模式和强度'
    return prefix + '服务暂不可用，请稍后重试；不会自动切换其他服务'


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
    session_id = kwargs.pop('session_id', None) or provider.get('session_id') or str(uuid.uuid4())
    try:
        extra = _extra_payload(provider)
    except ValueError as exc:
        raise AiError(str(exc)) from exc
    payload = {'model': provider.get('model', ''), 'messages': messages,
               'max_tokens': min(65536, max(1, int(max_tokens))), 'temperature': temperature,
               **extra, **kwargs}
    if extra.get('thinking', {}).get('type') == 'enabled' or ai_profiles.capabilities(provider)['control'] == 'always':
        payload.pop('temperature', None)
    headers = request_headers(provider, session_id)
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=30)) as client:
            while True:
                response = client.post(build_url(provider['base_url']), json=payload, headers=headers)
                if response.status_code >= 400:
                    # 错误文本不附带密钥或请求头。
                    raise AiError(response_error(response))
                try:
                    choice = response.json()['choices'][0]
                    message = choice['message']
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise AiError('AI 服务返回了无法识别的响应') from exc
                if not isinstance(message, dict):
                    raise AiError('AI 服务返回的消息格式错误，请重试')
                content = message.get('content') or ''
                if isinstance(content, list):
                    parts = [part.get('text', '') for part in content if isinstance(part, dict)]
                    if any(not isinstance(part, str) for part in parts):
                        raise AiError('AI 服务返回的正文格式错误，请重试')
                    content = ''.join(parts)
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
                     max_tokens=32000 if provider.get('model', '').lower().startswith('glm-5') or
                     (provider.get('reasoning_mode') != 'disabled' and ai_profiles.capabilities(provider)['control'] != 'none') else 256)
        return True, '连接成功：' + reply[:120]
    except AiError as exc:
        return False, str(exc)


def refresh_models(provider: dict) -> list[dict]:
    kind = ai_profiles.service_type(provider)
    if kind == 'opencode_go':
        url = 'https://opencode.ai/inference/go/v1/models'
    elif kind == 'deepseek':
        url = 'https://api.deepseek.com/models'
    else:
        raise AiError('该预设暂不支持在线刷新，可保留当前模型或手动输入模型名')
    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=15)) as client:
            response = client.get(url, headers=request_headers(provider, 'models-' + str(uuid.uuid4())))
        if response.status_code >= 400:
            raise AiError(response_error(response))
        items = response.json()['data']
        if not isinstance(items, list):
            raise ValueError('invalid models')
        result = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get('id'), str):
                # Go 目录也包含 Responses、Anthropic 等接口，仅展示本平台支持的 Chat Completions。
                if kind == 'opencode_go' and 'chat-completions' not in (item.get('api') or {}):
                    continue
                model = {k: item[k] for k in ('id', 'name', 'effort') if k in item}
                reasoning = (item.get('capabilities') or {}).get('reasoning') or {}
                if isinstance(reasoning.get('effort'), list):
                    model['effort'] = {'supported_levels': reasoning['effort']}
                result.append(model)
        if not result:
            raise ValueError('empty models')
        return result
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise AiError('模型列表刷新失败，已保留原配置，请检查网络后重试') from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise AiError('模型目录格式无法识别，已保留原配置') from exc
