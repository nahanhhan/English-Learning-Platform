use crate::{
    ai,
    api::{ApiError, ApiResult, text},
    codex, profiles,
};
use regex::Regex;
use serde_json::{Value, json};
use std::{sync::OnceLock, time::Instant};

pub fn policy() -> &'static Value {
    static POLICY: OnceLock<Value> = OnceLock::new();
    POLICY.get_or_init(|| {
        serde_json::from_str(include_str!("policies.json")).expect("valid grading policy")
    })
}

pub fn full_score(exam: &str, kind: &str) -> f64 {
    if exam == "ky2" && kind == "small_writing" {
        10.0
    } else {
        15.0
    }
}

pub fn rounded(value: f64) -> f64 {
    (value * 10.0).round_ties_even() / 10.0
}

pub fn band(score: f64) -> &'static str {
    match score {
        value if value >= 13.0 => "13-15分档",
        value if value >= 10.0 => "10-12分档",
        value if value >= 7.0 => "7-9分档",
        value if value >= 4.0 => "4-6分档",
        value if value > 0.0 => "1-3分档",
        _ => "0分",
    }
}

fn writing_band(score: f64, kind: &str) -> String {
    let integer = |value| {
        if kind != "small_writing" {
            return band(value);
        }
        match value {
            value if value >= 9.0 => "9-10分档",
            value if value >= 7.0 => "7-8分档",
            value if value >= 5.0 => "5-6分档",
            value if value >= 3.0 => "3-4分档",
            value if value > 0.0 => "1-2分档",
            _ => "0分",
        }
    };
    let (low, high) = (integer(score.floor()), integer(score.ceil()));
    if low == high {
        low.to_owned()
    } else {
        format!("{low}与{high}之间")
    }
}

pub fn score_reason(value: &Value) -> ApiResult<&str> {
    let reason = text(value, "score_reason").trim();
    if reason.is_empty() {
        Err(ApiError::bad(
            "批改缺少整体评分依据，作答已保留，请重新批改",
        ))
    } else {
        Ok(reason)
    }
}

fn count_words(value: &str) -> usize {
    static WORD: OnceLock<Regex> = OnceLock::new();
    WORD.get_or_init(|| Regex::new(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*").unwrap())
        .find_iter(value)
        .count()
}

fn word_range(prompt: &str, exam: &str, kind: &str) -> (usize, usize) {
    static RANGE: OnceLock<Regex> = OnceLock::new();
    static ABOUT: OnceLock<Regex> = OnceLock::new();
    if let Some(caps) = RANGE
        .get_or_init(|| {
            Regex::new(r"(?is)at\s+least\s+(\d+)\s+words.*?no\s+more\s+than\s+(\d+)\s+words")
                .unwrap()
        })
        .captures(prompt)
    {
        if let (Ok(low), Ok(high)) = (caps[1].parse::<usize>(), caps[2].parse::<usize>()) {
            if low > 0 && low <= high {
                return (low, high);
            }
        }
    }
    if let Some(caps) = ABOUT
        .get_or_init(|| Regex::new(r"(?i)about\s+(\d+)\s+words").unwrap())
        .captures(prompt)
    {
        if let Ok(low) = caps[1].parse::<usize>() {
            if low > 0 {
                return (low, (low as f64 * 1.3).round_ties_even() as usize);
            }
        }
    }
    if kind == "small_writing" {
        (100, 130)
    } else if exam == "ky2" {
        (150, 180)
    } else {
        (150, 200)
    }
}

fn string(value: &Value) -> String {
    if value.is_null() || value == false || value == 0 {
        String::new()
    } else {
        value
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| value.to_string())
    }
}

fn num(value: &Value) -> Option<f64> {
    value
        .as_f64()
        .or_else(|| value.as_str()?.trim().parse().ok())
        .filter(|number| number.is_finite())
}

pub fn strings(value: &Value) -> Vec<&str> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect()
}

pub fn project(value: &Value, fields: &[&str]) -> Value {
    Value::Object(
        fields
            .iter()
            .map(|field| (field.to_string(), json!(string(&value[*field]))))
            .collect(),
    )
}

pub fn dimensions(value: &Value, fields: &[&str]) -> Value {
    Value::Object(
        fields
            .iter()
            .map(|field| {
                (
                    field.to_string(),
                    json!(num(&value[*field]).unwrap_or(0.0).clamp(0.0, 5.0)),
                )
            })
            .collect(),
    )
}

fn normalize(mut result: Value, shape: &Value) -> Value {
    for (key, default) in shape.as_object().unwrap() {
        if default.is_array() && !result[key].is_array()
            || default.is_string() && !result[key].is_string()
        {
            result[key] = default.clone();
        }
    }
    let fields: Vec<_> = shape["dimensions"]
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    result["dimensions"] = dimensions(&result["dimensions"], &fields);
    for (key, fields) in [
        (
            "errors",
            &[
                "fragment",
                "issue_type",
                "explanation",
                "suggestion",
                "correction",
            ][..],
        ),
        ("key_notes", &["expr", "note"]),
        ("paragraph_comments", &["paragraph", "comment"]),
        ("vocab_upgrades", &["original", "upgrade", "note"]),
        (
            "optional_suggestions",
            &["original", "suggestion", "reason"],
        ),
    ] {
        if let Some(items) = result[key].as_array() {
            result[key] = json!(
                items
                    .iter()
                    .filter(|item| item.is_object())
                    .map(|item| project(item, fields))
                    .collect::<Vec<_>>()
            );
        }
    }
    if result.get("good_points").is_some() {
        result["good_points"] = json!(strings(&result["good_points"]));
    }
    result
}

pub fn mock(kind: &str, full: f64) -> Value {
    let translation = kind == "translation";
    let mut result = policy()[if translation {
        "translation_shape"
    } else {
        "writing_shape"
    }]
    .clone();
    result["score"] = json!(rounded(full * 0.7));
    result["band"] = json!("模拟批改示例");
    result["overall_comment"] =
        json!("这是用于体验流程的示例结果，未分析你的作答。请配置 AI 服务后重新批改。");
    for value in result["dimensions"].as_object_mut().unwrap().values_mut() {
        *value = json!(3.5);
    }
    if translation {
        result["improved_version"] = json!("此处将在真实批改后显示优化译文。");
    } else {
        result["polished_version"] = json!("此处将在真实批改后显示润色版全文。");
        result["model_essay"] = json!("此处将在真实批改后显示参考范文。");
    }
    result
}

pub fn messages(system: &str, user: &str) -> [Value; 2] {
    [
        json!({"role":"system","content":system}),
        json!({"role":"user","content":user}),
    ]
}

pub fn grade(submission: &Value, profile: &Value, session: &str, full: f64) -> ApiResult {
    let exam = text(submission, "exam_type");
    let kind = text(submission, "q_type");
    let prompt = text(submission, "prompt");
    let source = text(submission, "source_text");
    let content = text(submission, "content");
    let translation = kind == "translation";
    let bounds = (!translation).then(|| word_range(prompt, exam, kind));
    let policy = policy();
    let mut user = json!({"满分":full,"题目":prompt,"原文":source,"考生作答":content});
    let system = if let Some((low, high)) = bounds {
        user = json!({"满分":full,"题目":prompt,"补充材料":source,"考生作答":content,
            "原文字数":submission["word_count"],
            "要求":format!("评价切题、结构、语言、格式和语域。润色版保留原文核心论点和段落骨架，提升至最高档；润色版与独立参考范文均须在{low}-{high}词内。给出逐段点评、词汇升级及结构建议。")});
        "writing_system"
    } else if exam == "cet6" {
        "cet6_translation_system"
    } else {
        user["要求"] = json!("逐处核对忠实度、漏译、语言和流畅度，给出优化译文与关键表达点拨。");
        "ky2_translation_system"
    };
    let user = if system == "cet6_translation_system" {
        user.to_string()
    } else {
        let rubric = text(
            policy,
            match (exam, translation) {
                ("ky2", true) => "ky2_translation",
                (_, true) => "cet6_translation",
                ("ky2", false) => "ky2_writing",
                (_, false) => "cet6_writing",
            },
        );
        let mut rubric = rubric.to_owned();
        if exam == "ky2" && !translation {
            rubric.push('\n');
            rubric.push_str(if kind == "small_writing" {
                "应用文侧重要点、组织、准确性、格式和语体；语法词汇多样性的要求依题目调整。"
            } else {
                "短文侧重要点覆盖与阐述、组织连贯、语法词汇多样性和准确性。"
            });
            rubric.push_str("英美拼写与词汇用法均可接受；拼写标点按对交际的影响判断。电子文本不能判断手写卷面，不得臆测书写扣分。");
        }
        format!("评分标准：\n{rubric}\n\n{user}")
    };
    let local = profiles::kind(profile) == "codex";
    let deadline = local.then(|| Instant::now() + codex::TIMEOUT);
    let budget = if text(profile, "model").to_lowercase().starts_with("glm-5") {
        32000
    } else {
        8000
    };
    let raw = ai::extract_json(&ai::chat(
        profile,
        &messages(text(policy, system), &user),
        budget,
        session,
        deadline,
    )?)?;
    let requires_reason =
        exam == "cet6" || matches!(kind, "writing" | "small_writing" | "big_writing");
    let reason = if requires_reason {
        Some(score_reason(&raw)?.to_owned())
    } else {
        None
    };
    let score = num(&raw["score"]);
    if !translation && !score.is_some_and(|value| (0.0..=full).contains(&value)) {
        return Err(ApiError::bad(
            "作文分数不符合本题满分制，作答已保留，请重新批改",
        ));
    }
    let needed: &[&str] = if translation {
        &["overall_comment", "improved_version"]
    } else {
        &["overall_comment", "polished_version", "model_essay"]
    };
    if local
        && (!raw["score"].is_number() || needed.iter().any(|key| text(&raw, key).trim().is_empty()))
    {
        return Err(ApiError::bad("Codex 批改结果不完整，作答已保留，请重试"));
    }
    let mut score = score.unwrap_or(0.0);
    if full < score && score <= 100.0 {
        score = score / 100.0 * full;
    }
    score = rounded(score.clamp(0.0, full));
    let mut result = normalize(
        raw,
        &policy[if translation {
            "translation_shape"
        } else {
            "writing_shape"
        }],
    );
    result["score"] = json!(score);
    if let Some(reason) = reason {
        result["score_reason"] = json!(reason);
    }
    if translation && exam == "cet6" {
        result["band"] = json!(band(score));
        result["rubric_version"] = policy["cet6_translation_version"].clone();
    }
    if let Some((low, high)) = bounds {
        if matches!(exam, "cet6" | "ky2") {
            result["band"] = json!(writing_band(score, kind));
            result["rubric_version"] = policy[if exam == "cet6" {
                "cet6_writing_version"
            } else {
                "ky2_writing_version"
            }]
            .clone();
        }
        let mut warnings = Vec::new();
        for (field, label) in [("polished_version", "润色版"), ("model_essay", "参考范文")] {
            let original = text(&result, field);
            if (low..=high).contains(&count_words(original)) {
                continue;
            }
            let repair = format!(
                "按题目修订为最高档文章，保留核心论点和段落骨架。必须在{low}-{high}词内。\n题目：{prompt}\n原文：\n{original}"
            );
            match ai::chat(
                profile,
                &messages(
                    "你是英语写作教师。只输出修订后的英文全文，不添加标题、说明或代码围栏。",
                    &repair,
                ),
                4000,
                session,
                deadline,
            ) {
                Ok(answer) if (low..=high).contains(&count_words(&answer)) => {
                    result[field] = json!(answer)
                }
                Ok(_) => {
                    warnings.push(format!("{label}字数未达到{low}-{high}词要求，请检查后使用"))
                }
                Err(error) if deadline.is_some_and(|deadline| Instant::now() >= deadline) => {
                    return Err(error);
                }
                Err(_) => warnings.push(format!("{label}字数未达标，自动修复失败")),
            }
        }
        if !warnings.is_empty() {
            result["word_warnings"] = json!(warnings);
        }
    }
    Ok(result)
}
