use crate::{
    api::{ApiError, ApiResult, text, yes},
    codex,
};
use regex::Regex;
use serde_json::{Value, json};
use std::sync::OnceLock;
use url::Url;

pub const LEVELS: [&str; 7] = ["minimal", "low", "medium", "high", "xhigh", "max", "ultra"];
const GO: [&str; 13] = [
    "glm-5.3-flash",
    "glm-5.3",
    "glm-5.2",
    "kimi-k3.1-pro",
    "kimi-k3",
    "kimi-k2.7-code",
    "deepseek-v4.1-flash",
    "deepseek-v4-pro",
    "minimax-m3.1-flash",
    "longcat-2.0",
    "mimo-v2.6-flash",
    "mimo-v2.6-pro",
    "claude-haiku-5-5",
];
const CLAUDE: [&str; 5] = [
    "claude-haiku-5-5",
    "claude-sonnet-5-5",
    "claude-opus-5-5",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
];

pub fn kind(profile: &Value) -> &str {
    let selected = text(profile, "service_type");
    if !selected.is_empty() && selected != "custom" {
        return selected;
    }
    let Ok(url) = Url::parse(text(profile, "base_url")) else {
        return "custom";
    };
    match url.host_str() {
        Some("opencode.ai") if go_path(url.path()) => "opencode_go",
        Some("api.deepseek.com") => "deepseek",
        Some("open.bigmodel.cn") => "zhipu",
        Some("api.anthropic.com") => "anthropic",
        _ => "custom",
    }
}

fn go_path(path: &str) -> bool {
    path.starts_with("/zen/go/") || path.starts_with("/inference/go/")
}

pub fn catalogue(profile: &Value) -> Vec<Value> {
    let ids: &[&str] = match kind(profile) {
        "deepseek" => &["deepseek-flash", "deepseek-v4-pro"],
        "opencode_go" => &GO,
        "anthropic" => &CLAUDE,
        "zhipu" => &["glm-4.6", "glm-5.3-flash", "glm-5.3"],
        _ => &[],
    };
    let mut result: Vec<Value> = ids.iter().map(|id| json!({"id":id,"name":id})).collect();
    if let Ok(cache) = serde_json::from_str::<Vec<Value>>(text(profile, "models_json")) {
        for item in cache.into_iter().filter(|item| item["id"].is_string()) {
            if let Some(index) = result
                .iter()
                .position(|current| current["id"] == item["id"])
            {
                result[index] = item;
            } else {
                result.push(item);
            }
        }
    }
    let id = text(profile, "model");
    if !id.is_empty() && !result.iter().any(|item| item["id"] == id) {
        result.push(json!({"id":id,"name":id}));
    }
    result
}

fn model_info(profile: &Value) -> Value {
    catalogue(profile)
        .into_iter()
        .find(|item| text(item, "id").eq_ignore_ascii_case(text(profile, "model")))
        .unwrap_or(Value::Null)
}

pub fn messages(profile: &Value) -> bool {
    kind(profile) == "anthropic"
        || (kind(profile) == "opencode_go"
            && (text(profile, "model").to_lowercase().starts_with("claude-")
                || model_info(profile)["api_format"] == "messages"))
}

pub fn presets() -> Value {
    let presets = [
        json!({"name":"DeepSeek 官方","service_type":"deepseek","base_url":"https://api.deepseek.com","model":"deepseek-flash","docs":"https://api-docs.deepseek.com/guides/thinking_mode/"}),
        json!({"name":"OpenCode Go 订阅","service_type":"opencode_go","base_url":"https://opencode.ai/inference/go/openai/v1","model":"glm-5.3-flash","docs":"https://opencode.ai/v2/docs/console/go/"}),
        json!({"name":"Anthropic 官方","service_type":"anthropic","base_url":"https://api.anthropic.com","model":"claude-haiku-5-5","docs":"https://platform.claude.com/docs/en/build-with-claude/thinking"}),
        json!({"name":"智谱 GLM","service_type":"zhipu","base_url":"https://open.bigmodel.cn/api/paas/v4","model":"glm-4.6","docs":"https://docs.bigmodel.cn/"}),
    ];
    let profiles: Vec<_> = presets
        .iter()
        .cloned()
        .map(|mut profile| {
            profile["models"] = json!(catalogue(&profile));
            profile["capabilities"] = capabilities(&profile);
            profile
        })
        .collect();
    json!({"presets":presets,"profiles":profiles})
}

pub fn capabilities(profile: &Value) -> Value {
    let mut modes = vec!["auto"];
    let mut levels = Vec::new();
    let mut control = "none";
    let mut note = "能力未知，使用模型默认设置";
    let model = text(profile, "model").to_lowercase();
    let kind = kind(profile);
    let info = model_info(profile);
    let native = messages(profile);
    if native {
        static DATE: OnceLock<Regex> = OnceLock::new();
        let model = DATE
            .get_or_init(|| Regex::new(r"-\d{8}$").unwrap())
            .replace(&model, "");
        if CLAUDE.contains(&model.as_ref())
            || matches!(
                model.as_ref(),
                "claude-sonnet-5" | "claude-opus-5" | "claude-opus-4-8" | "claude-opus-4-7"
            )
        {
            modes.push("enabled");
            if !matches!(model.as_ref(), "claude-sonnet-5-5" | "claude-opus-5-5") {
                modes.push("disabled");
            }
            levels = vec!["low", "medium", "high", "max"];
            if !matches!(model.as_ref(), "claude-opus-4-6" | "claude-sonnet-4-6") {
                levels.insert(3, "xhigh");
            }
            control = "anthropic_adaptive";
            note = "支持 Claude 自适应推理和强度；未提供关闭选项的模型不能完全关闭推理";
        } else if matches!(
            model.as_ref(),
            "claude-haiku-4-5"
                | "claude-sonnet-4-5"
                | "claude-opus-4-5"
                | "claude-opus-4-1"
                | "claude-opus-4"
                | "claude-sonnet-4"
        ) {
            modes.extend(["enabled", "disabled"]);
            control = "anthropic_budget";
            note = "支持传统推理开关，开启时使用固定思考预算；此模型未确认支持强度";
        }
        if info["thinking"].is_object() {
            let thinking = &info["thinking"];
            modes = vec!["auto"];
            control = if yes(thinking, "adaptive") {
                "anthropic_adaptive"
            } else if yes(thinking, "enabled") {
                "anthropic_budget"
            } else {
                "none"
            };
            if control != "none" {
                modes.push("enabled");
            }
            if yes(thinking, "disabled") {
                modes.push("disabled");
            }
            note = "推理选项依据服务返回的模型能力";
        }
    } else {
        if matches!(kind, "deepseek" | "opencode_go")
            && matches!(
                model.as_str(),
                "deepseek-flash" | "deepseek-v4.1-flash" | "deepseek-v4-pro"
            )
        {
            modes.extend(["enabled", "disabled"]);
            levels = vec!["low", "high", "max"];
            control = "thinking";
            note = "支持推理开关；强度为低、高、最高";
        } else if model.starts_with("glm-5") {
            modes.push("enabled");
            control = "always";
            note = "模型强制推理，不能关闭；未确认可调强度";
        } else if model.starts_with("glm-4") {
            modes.extend(["enabled", "disabled"]);
            control = "thinking";
            note = "支持推理开关";
        }
        if kind == "opencode_go" {
            if matches!(model.as_str(), "deepseek-v4-pro" | "glm-5.2") {
                levels = vec!["high", "max"];
            }
            if matches!(model.as_str(), "glm-5.3" | "glm-5.3-flash") {
                levels = vec!["low", "high", "max"];
            }
            if model.starts_with("glm-5") {
                note = "模型强制推理，不能关闭；强度依据 Go 官方目录";
            }
        }
    }
    if let Some(declared) = info["effort"]["supported_levels"].as_array() {
        let available: Vec<_> = if native {
            LEVELS
                .into_iter()
                .filter(|name| declared.iter().any(|value| value == name))
                .collect()
        } else {
            declared
                .iter()
                .filter_map(Value::as_str)
                .filter_map(|name| LEVELS.into_iter().find(|level| *level == name))
                .collect()
        };
        if native || !available.is_empty() {
            levels = available;
        }
        if !levels.is_empty() && control == "none" {
            control = if native { "anthropic_effort" } else { "effort" };
            note = "服务已声明可用的推理强度，开关跟随模型默认";
        }
    }
    json!({"modes":modes,"levels":levels,"control":control,"note":note})
}

pub fn validate(profile: &Value) -> ApiResult<()> {
    let kind = kind(profile);
    if kind == "codex" {
        if text(profile, "reasoning_mode") != "auto" {
            return Err(ApiError::bad("Codex 不支持此推理模式"));
        }
        return codex::validate(text(profile, "model"), text(profile, "reasoning_effort"));
    }
    let url = Url::parse(text(profile, "base_url"))
        .ok()
        .filter(|url| {
            matches!(url.scheme(), "http" | "https")
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
        })
        .ok_or_else(|| ApiError::bad("请填写有效的 API 地址，不要把密钥放在地址中"))?;
    match kind {
        "opencode_go"
            if url.scheme() != "https"
                || url.host_str() != Some("opencode.ai")
                || !go_path(url.path()) =>
        {
            return Err(ApiError::bad("Go 订阅请选择官方的独立 Go 接口地址"));
        }
        "deepseek" if url.host_str() != Some("api.deepseek.com") => {
            return Err(ApiError::bad(
                "DeepSeek 官方预设请使用 api.deepseek.com；其他地址请选择自定义服务",
            ));
        }
        "anthropic" if url.scheme() != "https" || url.host_str() != Some("api.anthropic.com") => {
            return Err(ApiError::bad(
                "Anthropic 官方入口请使用 https://api.anthropic.com，Go 订阅请选择 OpenCode Go",
            ));
        }
        _ => {}
    }
    reasoning(profile)?;
    Ok(())
}

pub fn reasoning(profile: &Value) -> ApiResult<Value> {
    let native = messages(profile);
    let caps = capabilities(profile);
    let mode = profile["reasoning_mode"]
        .as_str()
        .filter(|value| !value.is_empty())
        .unwrap_or("auto");
    let effort = text(profile, "reasoning_effort");
    if !caps["modes"]
        .as_array()
        .unwrap()
        .iter()
        .any(|allowed| allowed == mode)
    {
        return Err(ApiError::bad(text(&caps, "note")));
    }
    let mut payload = json!({});
    let control = text(&caps, "control");
    if (native && mode == "disabled") || (control == "thinking" && mode != "auto") {
        payload["thinking"] = json!({"type":mode});
    } else if mode == "enabled" && control == "anthropic_adaptive" {
        payload["thinking"] = json!({"type":"adaptive"});
    } else if mode == "enabled" && control == "anthropic_budget" {
        payload["thinking"] = json!({"type":"enabled","budget_tokens":4096});
    }
    if mode != "disabled" && !effort.is_empty() {
        if !caps["levels"]
            .as_array()
            .unwrap()
            .iter()
            .any(|allowed| allowed == effort)
        {
            return Err(ApiError::bad(
                "该模型尚未声明支持此推理强度，请使用模型默认或刷新模型列表",
            ));
        }
        if native {
            payload["output_config"] = json!({"effort":effort});
        } else {
            payload["reasoning_effort"] = json!(effort);
        }
    }
    Ok(payload)
}
