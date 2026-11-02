"""服务预设和已确认的模型能力；未知模型只使用默认参数。"""
import json
from urllib.parse import urlsplit

DEEPSEEK_DOC = "https://api-docs.deepseek.com/guides/thinking_mode/"
GO_DOC = "https://opencode.ai/v2/docs/console/go/"
PRESETS = [
    {"name": "DeepSeek 官方", "service_type": "deepseek", "base_url": "https://api.deepseek.com", "model": "deepseek-flash", "docs": DEEPSEEK_DOC},
    {"name": "OpenCode Go 订阅", "service_type": "opencode_go", "base_url": "https://opencode.ai/inference/go/openai/v1", "model": "glm-5.3-flash", "docs": GO_DOC},
    {"name": "智谱 GLM", "service_type": "zhipu", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4.6", "docs": "https://docs.bigmodel.cn/"},
]
GO_MODELS = ["glm-5.3-flash", "glm-5.3", "glm-5.2", "kimi-k3.1-pro", "kimi-k3", "kimi-k2.7-code",
             "deepseek-v4.1-flash", "deepseek-v4-pro", "minimax-m3.1-flash", "longcat-2.0", "mimo-v2.6-flash", "mimo-v2.6-pro"]


def service_type(provider):
    kind = provider.get("service_type", "custom")
    if kind != "custom":
        return kind
    url = urlsplit(provider.get("base_url", ""))
    if url.hostname == "opencode.ai" and (url.path.startswith("/zen/go/") or url.path.startswith("/inference/go/")):
        return "opencode_go"
    if url.hostname == "api.deepseek.com":
        return "deepseek"
    if url.hostname == "open.bigmodel.cn":
        return "zhipu"
    return "custom"


def config(provider, session_id=None):
    result = {key: getattr(provider, key, "") for key in
              ("name", "base_url", "api_key", "model", "service_type", "reasoning_mode", "reasoning_effort", "models_json")}
    if session_id:
        result["session_id"] = session_id
    return result


def catalogue(provider):
    kind = service_type(provider)
    ids = (["deepseek-flash", "deepseek-v4-pro"] if kind == "deepseek" else
           GO_MODELS if kind == "opencode_go" else ["glm-4.6", "glm-5.3-flash", "glm-5.3"] if kind == "zhipu" else [])
    try:
        cache = json.loads(provider.get("models_json") or "[]")
    except (ValueError, TypeError):
        cache = []
    models = {name: {"id": name, "name": name} for name in ids}
    for item in cache if isinstance(cache, list) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            models[item["id"]] = item
    if provider.get("model"):
        models.setdefault(provider["model"], {"id": provider["model"], "name": provider["model"]})
    return list(models.values())


def capabilities(provider):
    model = provider.get("model", "").lower()
    kind = service_type(provider)
    result = {"modes": ["auto"], "levels": [], "control": "none", "note": "能力未知，使用模型默认设置"}
    if kind in ("deepseek", "opencode_go") and model in {"deepseek-flash", "deepseek-v4.1-flash", "deepseek-v4-pro"}:
        result = {"modes": ["auto", "enabled", "disabled"], "levels": ["low", "high", "max"], "control": "thinking", "note": "支持推理开关；强度为低、高、最高"}
    elif model.startswith("glm-5"):
        result = {"modes": ["auto", "enabled"], "levels": [], "control": "always", "note": "模型强制推理，不能关闭；未确认可调强度"}
    elif model.startswith("glm-4"):
        result = {"modes": ["auto", "enabled", "disabled"], "levels": [], "control": "thinking", "note": "支持推理开关"}
    # 同名模型在订阅服务上的强度可能与官方不同，以 Go 目录为准。
    if kind == "opencode_go":
        if model == "deepseek-v4-pro" or model == "glm-5.2":
            result["levels"] = ["high", "max"]
        elif model in ("glm-5.3", "glm-5.3-flash"):
            result["levels"] = ["low", "high", "max"]
        if model.startswith("glm-5"):
            result["note"] = "模型强制推理，不能关闭；强度依据 Go 官方目录"
    # 仅从服务返回的明确 effort 元数据扩展强度，不猜测 unsupported 参数。
    item = next((m for m in catalogue(provider) if m["id"].lower() == model), {})
    effort = item.get("effort")
    if isinstance(effort, dict) and isinstance(effort.get("supported_levels"), list):
        levels = [v for v in effort["supported_levels"] if isinstance(v, str) and v in {"minimal", "low", "medium", "high", "xhigh", "max", "ultra"}]
        if levels:
            result["levels"] = levels
            if result["control"] == "none":
                result.update(control="effort", note="服务已声明可用的推理强度，开关跟随模型默认")
    return result


def validate(provider):
    url = urlsplit(provider.get("base_url", ""))
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("请填写有效的 API 地址，不要把密钥放在地址中")
    kind = service_type(provider)
    if kind == "opencode_go" and (url.scheme != "https" or url.hostname != "opencode.ai" or not
        (url.path.startswith("/zen/go/") or url.path.startswith("/inference/go/"))):
        raise ValueError("Go 订阅请选择官方的独立 Go 接口地址")
    if kind == "deepseek" and url.hostname != "api.deepseek.com":
        raise ValueError("DeepSeek 官方预设请使用 api.deepseek.com；其他地址请选择自定义服务")
    caps = capabilities(provider)
    mode = provider.get("reasoning_mode") or "auto"
    if mode not in caps["modes"]:
        raise ValueError(caps["note"])
    effort = provider.get("reasoning_effort") or ""
    if mode != "disabled" and effort and effort not in caps["levels"]:
        raise ValueError("该模型尚未声明支持此推理强度，请使用模型默认或刷新模型列表")


def reasoning_payload(provider):
    # 对旧调用保留原有 GLM-4 关闭推理行为。
    if "reasoning_mode" not in provider:
        return {"thinking": {"type": "disabled"}} if provider.get("model", "").lower().startswith("glm-4") else {}
    caps = capabilities(provider)
    mode = provider.get("reasoning_mode") or "auto"
    effort = provider.get("reasoning_effort") or ""
    if mode not in caps["modes"]:
        raise ValueError(caps["note"])
    payload = {}
    if caps["control"] == "thinking" and mode != "auto":
        payload["thinking"] = {"type": mode}
    if mode != "disabled" and effort:
        if effort not in caps["levels"]:
            raise ValueError("模型不支持当前推理强度")
        payload["reasoning_effort"] = effort
    return payload
