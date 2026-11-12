use crate::{
    api::{ApiError, ApiResult, text},
    codex, profiles,
};
use regex::Regex;
use reqwest::{
    Method,
    blocking::{Client, Response},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::HashSet,
    sync::OnceLock,
    time::{Duration, Instant},
};

fn request_url(profile: &Value) -> String {
    static VERSION: OnceLock<Regex> = OnceLock::new();
    let base = text(profile, "base_url").trim().trim_end_matches('/');
    let native = profiles::messages(profile);
    if profiles::kind(profile) == "opencode_go" {
        if native {
            return "https://opencode.ai/inference/go/anthropic/v1/messages".into();
        }
        if base.contains("/anthropic/") {
            return "https://opencode.ai/inference/go/openai/v1/chat/completions".into();
        }
    }
    if native {
        return if base.ends_with("/messages") {
            base.to_owned()
        } else if base.ends_with("/v1") {
            format!("{base}/messages")
        } else {
            format!("{base}/v1/messages")
        };
    }
    if base.ends_with("/chat/completions") {
        return base.to_owned();
    }
    if VERSION
        .get_or_init(|| Regex::new(r"(?i)/v\d+(?:[a-z][\w.-]*)?$").unwrap())
        .is_match(base)
    {
        format!("{base}/chat/completions")
    } else {
        format!("{base}/v1/chat/completions")
    }
}

fn http_error(error: reqwest::Error) -> ApiError {
    ApiError::bad(if error.is_timeout() {
        "AI 请求超时，请稍后重试"
    } else {
        "无法连接 AI 服务，请检查地址和网络"
    })
}

fn client() -> ApiResult<&'static Client> {
    static CLIENT: OnceLock<Option<Client>> = OnceLock::new();
    CLIENT
        .get_or_init(|| {
            Client::builder()
                .connect_timeout(Duration::from_secs(15))
                .redirect(reqwest::redirect::Policy::none())
                .build()
                .ok()
        })
        .as_ref()
        .ok_or_else(|| ApiError::bad("无法初始化本机 AI 网络连接"))
}

fn request(
    method: Method,
    endpoint: &str,
    profile: &Value,
    session: &str,
    timeout: Duration,
) -> ApiResult<reqwest::blocking::RequestBuilder> {
    let mut request = client()?
        .request(method, endpoint)
        .timeout(timeout)
        .bearer_auth(text(profile, "api_key"));
    if profiles::messages(profile) {
        request = request.header("anthropic-version", "2026-10-21");
    }
    if profiles::kind(profile) == "opencode_go" {
        request = request
            .header("User-Agent", "EnglishLearningPlatform/1.0")
            .header("x-opencode-session", session);
    }
    Ok(request)
}

fn response(response: Response) -> ApiResult<Value> {
    let status = response.status().as_u16();
    if status >= 400 {
        let detail = response
            .json::<Value>()
            .map(|value| value.to_string().to_lowercase())
            .unwrap_or_default();
        let message = if detail.contains("missingsession") || detail.contains("x-opencode-session")
        {
            "Go 会话请求头未被接受，请检查连接测试及订阅接口"
        } else {
            match status {
                401 => "认证失败，请检查密钥是否有效或已过期",
                403 => "没有模型访问权限，或该服务不支持当前用途，请核对账户权限及适用范围",
                402 | 429 => "额度不足或请求过于频繁，请检查订阅额度、余额或稍后重试",
                400 => "请求参数不被模型支持，请检查模型、推理模式和强度",
                _ => "服务暂不可用，请稍后重试",
            }
        };
        return Err(ApiError::bad(format!(
            "AI 服务返回 HTTP {status}：{message}"
        )));
    }
    response
        .json()
        .map_err(|_| ApiError::bad("AI 服务返回了无法识别的响应"))
}

fn native_response(data: &Value) -> ApiResult<(String, bool)> {
    let reason = text(data, "stop_reason");
    if reason == "refusal" {
        return Err(ApiError::bad(
            "Claude 未接受本次请求，作答已保留；请检查服务适用范围或手动重试",
        ));
    }
    if !matches!(reason, "end_turn" | "stop_sequence" | "max_tokens") {
        return Err(ApiError::bad("Claude 未返回完整批改结果，请手动重试"));
    }
    let blocks = data["content"]
        .as_array()
        .ok_or_else(|| ApiError::bad("Claude 返回的响应格式错误，请重试"))?;
    let mut answer = String::new();
    for block in blocks {
        if !block.is_object() {
            return Err(ApiError::bad("Claude 返回的响应格式错误，请重试"));
        }
        if block["type"] == "text" {
            answer.push_str(
                block["text"]
                    .as_str()
                    .ok_or_else(|| ApiError::bad("Claude 返回的正文格式错误，请重试"))?,
            );
        }
    }
    Ok((answer, reason == "max_tokens"))
}

fn completion_response(data: &Value) -> ApiResult<(String, bool)> {
    let choice = data["choices"]
        .get(0)
        .filter(|value| value["message"].is_object())
        .ok_or_else(|| ApiError::bad("AI 服务返回了无法识别的响应"))?;
    let content = &choice["message"]["content"];
    let truncated = choice["finish_reason"] == "length";
    let answer = if let Some(content) = content.as_str() {
        content.to_owned()
    } else if let Some(parts) = content.as_array() {
        let strings = parts
            .iter()
            .filter(|part| part.is_object())
            .map(|part| {
                part.get("text")
                    .map_or(Some(""), Value::as_str)
                    .ok_or_else(|| ApiError::bad("AI 服务返回的正文格式错误，请重试"))
            })
            .collect::<ApiResult<Vec<_>>>()?;
        strings.concat()
    } else {
        String::new()
    };
    Ok((answer, truncated))
}

pub fn chat(
    profile: &Value,
    messages: &[Value],
    mut budget: u64,
    session: &str,
    deadline: Option<Instant>,
) -> ApiResult<String> {
    profiles::validate(profile)?;
    if profiles::kind(profile) == "codex" {
        return codex::complete(
            messages,
            text(profile, "model"),
            text(profile, "reasoning_effort"),
            deadline.unwrap_or_else(|| Instant::now() + codex::TIMEOUT),
        );
    }
    let native = profiles::messages(profile);
    let mut body = profiles::reasoning(profile)?;
    body["model"] = profile["model"].clone();
    if native {
        let system: Vec<_> = messages
            .iter()
            .filter(|msg| matches!(text(msg, "role"), "system" | "developer"))
            .map(|msg| text(msg, "content"))
            .collect();
        if !system.is_empty() {
            body["system"] = json!(system.join("\n\n"));
        }
        body["messages"] = json!(
            messages
                .iter()
                .filter(|msg| matches!(text(msg, "role"), "user" | "assistant"))
                .collect::<Vec<_>>()
        );
        body["stream"] = json!(false);
        budget = budget.max(body["thinking"]["budget_tokens"].as_u64().unwrap_or(0) + 1);
    } else {
        body["messages"] = json!(messages);
        if body["thinking"]["type"] != "enabled"
            && profiles::capabilities(profile)["control"] != "always"
        {
            body["temperature"] = json!(0.3);
        }
    }
    let endpoint = request_url(profile);
    loop {
        body["max_tokens"] = json!(budget);
        let response = request(
            Method::POST,
            &endpoint,
            profile,
            session,
            Duration::from_secs(300),
        )?
        .json(&body)
        .send()
        .map_err(http_error)?;
        let data = self::response(response)?;
        let (answer, truncated) = if native {
            native_response(&data)?
        } else {
            completion_response(&data)?
        };
        if truncated {
            if budget >= 65536 {
                return Err(ApiError::bad(
                    "AI 输出达到长度上限，请换用更合适的模型或缩短作答后重试",
                ));
            }
            budget = (budget * 2).min(65536);
        } else if answer.trim().is_empty() {
            return Err(ApiError::bad("AI 返回正文为空，请检查模型或重试"));
        } else {
            return Ok(answer.trim().to_owned());
        }
    }
}

pub fn extract_json(answer: &str) -> ApiResult<Value> {
    for (index, _) in answer.match_indices('{') {
        let mut json = serde_json::Deserializer::from_str(&answer[index..]);
        if let Ok(value @ Value::Object(_)) = Value::deserialize(&mut json) {
            return Ok(value);
        }
    }
    Err(ApiError::bad(
        "AI 返回的内容不是有效的 JSON 对象，请重试批改",
    ))
}

fn model_metadata(item: &Value, kind: &str) -> Option<Value> {
    let id = item["id"].as_str()?;
    let mut model = json!({"id":id});
    if let Some(name) = item["display_name"].as_str().or(item["name"].as_str()) {
        model["name"] = json!(name);
    }
    if kind == "opencode_go" {
        let api = item["api"].as_object()?;
        model["api_format"] = if api.contains_key("messages")
            && (id.starts_with("claude-") || !api.contains_key("chat-completions"))
        {
            json!("messages")
        } else if api.contains_key("chat-completions") {
            json!("chat-completions")
        } else {
            return None;
        };
    } else if kind == "anthropic" {
        model["api_format"] = json!("messages");
    }
    let caps = &item["capabilities"];
    let declared = caps["reasoning"]["effort"]
        .as_array()
        .or(item["effort"]["supported_levels"].as_array());
    if let Some(declared) = declared {
        model["effort"] = json!({"supported_levels":profiles::LEVELS.into_iter().filter(|level|declared.iter().any(|value|value==level)).collect::<Vec<_>>()});
    } else if caps["effort"].get("supported").is_some() {
        model["effort"] = json!({"supported_levels":profiles::LEVELS.into_iter()
            .filter(|level|caps["effort"][*level]["supported"]==true).collect::<Vec<_>>()});
    }
    if kind == "anthropic" && caps["thinking"]["types"].is_object() {
        let types = &caps["thinking"]["types"];
        model["thinking"] = json!({"adaptive":types["adaptive"]["supported"]==true,
            "enabled":types["enabled"]["supported"]==true,"disabled":types["disabled"]["supported"]==true});
    }
    Some(model)
}

pub fn refresh(profile: &Value) -> ApiResult<Vec<Value>> {
    profiles::validate(profile)?;
    let kind = profiles::kind(profile);
    let initial = match kind {
        "opencode_go" => "https://opencode.ai/inference/go/v1/models",
        "deepseek" => "https://api.deepseek.com/models",
        "anthropic" => "https://api.anthropic.com/v1/models?limit=100",
        _ => {
            return Err(ApiError::bad(
                "该预设暂不支持在线刷新，可保留当前模型或手动输入模型名",
            ));
        }
    };
    let session = format!("models-{}", uuid::Uuid::new_v4());
    let mut endpoint = initial.to_owned();
    let mut models = Vec::new();
    let mut cursors = HashSet::new();
    loop {
        let result = request(
            Method::GET,
            &endpoint,
            profile,
            &session,
            Duration::from_secs(30),
        )?
        .send()
        .map_err(http_error)?;
        let payload = response(result)?;
        let items = payload["data"]
            .as_array()
            .ok_or_else(|| ApiError::bad("模型目录格式无法识别，已保留原配置"))?;
        models.extend(items.iter().filter_map(|item| model_metadata(item, kind)));
        if kind != "anthropic" || payload["has_more"] != true {
            break;
        }
        let cursor = payload["last_id"]
            .as_str()
            .filter(|value| {
                !value.is_empty() && cursors.insert(value.to_string()) && cursors.len() <= 20
            })
            .ok_or_else(|| ApiError::bad("模型目录分页异常，已保留原配置"))?;
        let mut url = url::Url::parse(initial).unwrap();
        url.query_pairs_mut().append_pair("after_id", cursor);
        endpoint = url.to_string();
    }
    if models.is_empty() {
        return Err(ApiError::bad("模型目录为空，已保留原配置"));
    }
    Ok(models)
}
