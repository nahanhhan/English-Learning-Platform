"""Chat Completions 与 Anthropic Messages 调用，共用会话、错误和重试。"""
import json
import re
import uuid
from urllib.parse import urlencode

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


def request_url(provider: dict) -> str:
    native = ai_profiles.api_format(provider) == 'messages'
    base = provider['base_url'].strip().rstrip('/')
    if ai_profiles.service_type(provider) == 'opencode_go':
        if native:
            return 'https://opencode.ai/inference/go/anthropic/v1/messages'
        if '/anthropic/' in base:
            return 'https://opencode.ai/inference/go/openai/v1/chat/completions'
    if not native:
        return build_url(base)
    if base.endswith('/messages'):
        return base
    return base + ('/messages' if base.endswith('/v1') else '/v1/messages')


def request_headers(provider: dict, session_id: str) -> dict:
    headers = {'Authorization': 'Bearer ' + provider.get('api_key', ''), 'Content-Type': 'application/json'}
    if ai_profiles.api_format(provider) == 'messages':
        headers['anthropic-version'] = '2026-10-21'
    if ai_profiles.service_type(provider) == 'opencode_go':
        headers.update({'User-Agent': 'EnglishLearningPlatform/1.0', 'x-opencode-session': session_id})
    return headers


def messages_payload(provider, messages, max_tokens, extra, kwargs):
    system, turns = [], []
    for item in messages:
        if not isinstance(item, dict) or not isinstance(item.get('content'), str):
            raise AiError('Claude 请求消息格式错误')
        role = item.get('role')
        if role in ('system', 'developer'):
            system.append(item['content'])
        elif role in ('user', 'assistant'):
            turns.append({'role': role, 'content': item['content']})
        else:
            raise AiError('Claude 请求包含不支持的消息类型')
    if not turns:
        raise AiError('Claude 请求缺少作答消息')
    payload = {'model': provider.get('model', ''), 'messages': turns, 'max_tokens': max_tokens,
               **extra, **kwargs, 'stream': False}
    if system:
        payload['system'] = '\n\n'.join(system)
    budget = extra.get('thinking', {}).get('budget_tokens', 0)
    payload['max_tokens'] = max(max_tokens, budget + 1)
    # 新 Claude 模型不接受自定义采样参数；推理配置由专用字段控制。
    for key in ('temperature', 'top_p', 'top_k', 'reasoning_effort'):
        payload.pop(key, None)
    return payload


def messages_response(response):
    try:
        data = response.json()
        blocks, reason = data['content'], data['stop_reason']
        if not isinstance(blocks, list):
            raise ValueError('invalid content')
        parts = []
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError('invalid block')
            if block.get('type') == 'text':
                if not isinstance(block.get('text'), str):
                    raise ValueError('invalid text')
                parts.append(block['text'])
    except (ValueError, KeyError, TypeError) as exc:
        raise AiError('Claude 返回的响应格式错误，请重试') from exc
    if reason == 'refusal':
        raise AiError('Claude 未接受本次请求，作答已保留；请检查服务适用范围或手动重试')
    if reason not in ('end_turn', 'stop_sequence', 'max_tokens'):
        raise AiError('Claude 未返回完整批改结果，请手动重试')
    return ''.join(parts), reason == 'max_tokens'


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
    if ai_profiles.service_type(provider) == "codex":
        from .codex_provider import complete
        return complete(messages, provider.get("deadline"), provider.get("model", ""),
                        provider.get("reasoning_effort", ""))
    session_id = kwargs.pop('session_id', None) or provider.get('session_id') or str(uuid.uuid4())
    try:
        extra = _extra_payload(provider)
    except ValueError as exc:
        raise AiError(str(exc)) from exc
    payload = {'model': provider.get('model', ''), 'messages': messages,
               'max_tokens': min(65536, max(1, int(max_tokens))), 'temperature': temperature,
               **extra, **kwargs}
    native = ai_profiles.api_format(provider) == 'messages'
    if native:
        payload = messages_payload(provider, messages, payload['max_tokens'], extra, kwargs)
    if extra.get('thinking', {}).get('type') == 'enabled' or ai_profiles.capabilities(provider)['control'] == 'always':
        payload.pop('temperature', None)
    headers = request_headers(provider, session_id)
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=30)) as client:
            while True:
                response = client.post(request_url(provider), json=payload, headers=headers)
                if response.status_code >= 400:
                    # 错误文本不附带密钥或请求头。
                    raise AiError(response_error(response))
                if native:
                    content, truncated = messages_response(response)
                else:
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
                    truncated = choice.get('finish_reason') == 'length'
                # 思考耗尽配额时重试；截断的非空 JSON 同样不能直接用于评分。
                if truncated:
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
                     max_tokens=32000 if ai_profiles.api_format(provider) == 'messages' or provider.get('model', '').lower().startswith('glm-5') or
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
    elif kind == 'anthropic':
        url = 'https://api.anthropic.com/v1/models?limit=100'
    else:
        raise AiError('该预设暂不支持在线刷新，可保留当前模型或手动输入模型名')
    try:
        result, cursors = [], set()
        headers = request_headers(provider, 'models-' + str(uuid.uuid4()))
        with httpx.Client(timeout=httpx.Timeout(30, connect=15)) as client:
            while True:
                response = client.get(url, headers=headers)
                if response.status_code >= 400:
                    raise AiError(response_error(response))
                body = response.json()
                items = body['data']
                if not isinstance(items, list):
                    raise ValueError('invalid models')
                for item in items:
                    model = model_metadata(item, kind)
                    if model:
                        result.append(model)
                if kind != 'anthropic' or not body.get('has_more'):
                    break
                cursor = body.get('last_id')
                if not isinstance(cursor, str) or not cursor or cursor in cursors or len(cursors) >= 20:
                    raise ValueError('invalid pagination')
                cursors.add(cursor)
                url = 'https://api.anthropic.com/v1/models?' + urlencode({'limit': 100, 'after_id': cursor})
        if not result:
            raise ValueError('empty models')
        return result
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise AiError('模型列表刷新失败，已保留原配置，请检查网络后重试') from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise AiError('模型目录格式无法识别，已保留原配置') from exc


def model_metadata(item, kind):
    """仅缓存经过核对的能力字段，不保存外部目录中的任意配置。"""
    if not isinstance(item, dict) or not isinstance(item.get('id'), str):
        return None
    model = {'id': item['id']}
    name = item.get('display_name') or item.get('name')
    if isinstance(name, str):
        model['name'] = name
    if kind == 'opencode_go':
        apis = item.get('api') or {}
        if not isinstance(apis, dict):
            return None
        if 'messages' in apis and (item['id'].startswith('claude-') or 'chat-completions' not in apis):
            model['api_format'] = 'messages'
        elif 'chat-completions' in apis:
            model['api_format'] = 'chat-completions'
        else:
            return None
    elif kind == 'anthropic':
        model['api_format'] = 'messages'
    caps = item.get('capabilities') or {}
    if not isinstance(caps, dict):
        raise ValueError('invalid capabilities')
    reasoning = caps.get('reasoning') or {}
    effort = caps.get('effort') or {}
    if isinstance(reasoning, dict) and isinstance(reasoning.get('effort'), list):
        model['effort'] = {'supported_levels': [v for v in ai_profiles.EFFORT_LEVELS if v in reasoning['effort']]}
    elif isinstance(effort, dict) and 'supported' in effort:
        model['effort'] = {'supported_levels': [v for v in ai_profiles.EFFORT_LEVELS
                           if isinstance(effort.get(v), dict) and effort[v].get('supported') is True]}
    elif isinstance(item.get('effort'), dict) and isinstance(item['effort'].get('supported_levels'), list):
        model['effort'] = {'supported_levels': [v for v in ai_profiles.EFFORT_LEVELS if v in item['effort']['supported_levels']]}
    thinking = caps.get('thinking') or {}
    types = thinking.get('types') if isinstance(thinking, dict) else None
    if kind == 'anthropic' and isinstance(types, dict):
        model['thinking'] = {key: isinstance(types.get(key), dict) and types[key].get('supported') is True
                             for key in ('adaptive', 'enabled', 'disabled')}
    return model
