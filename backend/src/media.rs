use crate::{
    api::{ApiError, ApiResult, App, text},
    process,
};
use axum::{
    body::Body,
    http::{StatusCode, header},
    response::Response,
};
use regex::Regex;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    fs,
    path::Path,
    process::Command,
    sync::{Condvar, Mutex, OnceLock},
    time::Duration,
};
use unicode_normalization::UnicodeNormalization;

#[derive(Default)]
pub struct SpeechGate {
    active: Mutex<HashSet<String>>,
    changed: Condvar,
}

pub fn document(app: &App, filename: &str, input: Vec<u8>) -> ApiResult {
    if input.len() > 30 * 1024 * 1024 {
        return Err(ApiError::new(
            413,
            "文件过大，请按课程拆分为 30 MB 以内后导入",
        ));
    }
    if input.is_empty() {
        return Err(ApiError::bad("文件为空"));
    }
    let name = filename.rsplit(['/', '\\']).next().unwrap_or_default();
    if name.to_lowercase().ends_with(".doc") {
        return Err(ApiError::bad("旧版 Word .doc 请先另存为 .docx 后导入"));
    }
    if !matches!(
        Path::new(name)
            .extension()
            .and_then(|ext| ext.to_str())
            .map(str::to_ascii_lowercase)
            .as_deref(),
        Some("pdf" | "docx")
    ) {
        return Err(ApiError::bad("请选择 PDF 或 Word .docx 文件"));
    }
    worker(app, "document", name, input, Duration::from_secs(180))
}

fn worker(app: &App, task: &str, arg: &str, input: Vec<u8>, timeout: Duration) -> ApiResult {
    let interpreter = app.backend.join(if cfg!(windows) {
        ".venv/Scripts/python.exe"
    } else {
        ".venv/bin/python"
    });
    if !interpreter.is_file() {
        return Err(ApiError::new(
            503,
            "请先运行 setup.bat 安装文档识别和语音组件",
        ));
    }
    let output = process::output(
        Command::new(interpreter)
            .arg("-B")
            .arg(app.backend.join("tools/media.py"))
            .args([task, arg])
            .current_dir(&app.backend)
            .env("ENGLISH_PLATFORM_DATA_DIR", &app.storage),
        input,
        timeout,
    )
    .map_err(|_| ApiError::new(503, "媒体处理暂时不可用，请稍后重试"))?;
    let result: Value = serde_json::from_slice(&output.stdout)
        .map_err(|_| ApiError::new(503, "媒体处理暂时不可用，请稍后重试"))?;
    if output.status.success() {
        Ok(result)
    } else {
        Err(ApiError::new(
            result["status"]
                .as_u64()
                .filter(|value| (400..=599).contains(value))
                .unwrap_or(503) as u16,
            result["detail"]
                .as_str()
                .unwrap_or("媒体处理暂时不可用，请稍后重试"),
        ))
    }
}

fn normalize(input: &str) -> String {
    static ABBREVIATIONS: OnceLock<Regex> = OnceLock::new();
    static PUNCTUATION: OnceLock<Regex> = OnceLock::new();
    let input = input.nfkc().collect::<String>().replace('’', "'");
    let replaced = ABBREVIATIONS
        .get_or_init(|| Regex::new(r"(?i)\b(sb|sth)\b\.?").unwrap())
        .replace_all(&input, |m: &regex::Captures| {
            if m[1].eq_ignore_ascii_case("sb") {
                "somebody"
            } else {
                "something"
            }
        });
    let input = replaced
        .replace('/', " or ")
        .replace(['(', ')', '（', '）'], " ");
    PUNCTUATION
        .get_or_init(|| Regex::new(r"\.{2,}|…+|[\x00-\x1f\x7f]").unwrap())
        .replace_all(&input, " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn is_mp3(data: &[u8]) -> bool {
    data.len() >= 256 && (data.starts_with(b"ID3") || data[0] == 0xff && data[1] & 0xe0 == 0xe0)
}

fn audio(data: Vec<u8>, voice: &str, cached: bool) -> ApiResult<Response<Body>> {
    if !is_mp3(&data) {
        return Err(ApiError::new(503, "没有收到完整的语音音频"));
    }
    Ok(Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, "audio/mpeg")
        .header("X-Speech-Voice", voice)
        .header("X-Speech-Cache", if cached { "HIT" } else { "MISS" })
        .body(Body::from(data))
        .unwrap())
}

pub fn speech(app: &App, body: &Value) -> ApiResult<Response<Body>> {
    let raw = text(body, "text");
    if raw.is_empty() || raw.chars().count() > 1000 {
        return Err(ApiError::new(422, "朗读文本长度必须为 1 至 1000 个字符"));
    }
    let accent = body["accent"].as_str().unwrap_or("us");
    let voice = match accent {
        "us" => "en-US-JennyNeural",
        "uk" => "en-GB-SoniaNeural",
        _ => return Err(ApiError::new(422, "请选择美式或英式发音")),
    };
    let sense = body["sense"].as_str();
    if sense.is_some_and(|sense| sense != "purpose") {
        return Err(ApiError::new(422, "朗读语境无效"));
    }
    if accent == "us" && sense == Some("purpose") && raw.trim().eq_ignore_ascii_case("sake") {
        let path = app.data.join("pronunciations/sake-purpose-us.mp3");
        return audio(
            fs::read(path).map_err(|_| ApiError::new(503, "本地读音文件不可用"))?,
            voice,
            true,
        );
    }
    let spoken = normalize(raw);
    if spoken.is_empty() {
        return Err(ApiError::bad("请输入需要朗读的英文"));
    }
    // 保留原缓存键的 JSON 序列化格式，旧版已生成的读音可以直接播放。
    let fields =
        ["speech-text-v1", &spoken, voice, "-5%", "+0Hz"].map(|value| json!(value).to_string());
    let cache_key = format!(
        "{:x}",
        Sha256::digest(format!("[{}]", fields.join(", ")).as_bytes())
    );
    let path = app
        .storage
        .join("speech-cache")
        .join(format!("{cache_key}.mp3"));
    let unavailable = || ApiError::new(503, "发音暂时不可用，请稍后点击发音按钮重试");
    let mut active = app.speech.active.lock().map_err(|_| unavailable())?;
    loop {
        if let Ok(data) = fs::read(&path) {
            if is_mp3(&data) {
                return audio(data, voice, true);
            }
        }
        if active.len() < 2 && !active.contains(&cache_key) {
            break;
        }
        active = app.speech.changed.wait(active).map_err(|_| unavailable())?;
    }
    active.insert(cache_key.clone());
    drop(active);
    let result = worker(
        app,
        "speech",
        accent,
        raw.as_bytes().to_vec(),
        Duration::from_secs(35),
    );
    if let Ok(mut active) = app.speech.active.lock() {
        active.remove(&cache_key);
    }
    app.speech.changed.notify_all();
    result?;
    audio(fs::read(path).map_err(|_| unavailable())?, voice, false)
}
