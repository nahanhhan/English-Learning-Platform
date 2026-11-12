use crate::{
    ai,
    api::{ApiError, ApiResult, App, db_result, text, yes},
    codex, db, profiles,
};
use rusqlite::{Connection, params};
use serde_json::{Map, Value, json};
use std::time::Duration;

pub fn selected(db: &Connection, id: Option<i64>) -> ApiResult<Option<Value>> {
    Ok(match id {
        Some(id) => db::one(db, "SELECT * FROM ai_providers WHERE id=?1", [id])?,
        None => db::one(
            db,
            "SELECT * FROM ai_providers ORDER BY is_default DESC,id LIMIT 1",
            [],
        )?,
    })
}

fn provider(db: &Connection, id: i64) -> ApiResult {
    selected(db, Some(id))?.ok_or_else(|| ApiError::missing("服务商不存在"))
}

fn id(value: &str) -> ApiResult<i64> {
    value
        .parse()
        .map_err(|_| ApiError::new(422, "服务编号必须为整数"))
}

fn mask(key: &str) -> String {
    let chars: Vec<_> = key.chars().collect();
    match chars.len() {
        0 => String::new(),
        1..=8 => format!("{}****", chars.iter().take(2).collect::<String>()),
        size => format!(
            "{}****{}",
            chars[..4].iter().collect::<String>(),
            chars[size - 4..].iter().collect::<String>()
        ),
    }
}

fn payload(profile: &Value) -> Value {
    json!({"id":profile["id"],"name":profile["name"],"base_url":profile["base_url"],"model":profile["model"],
        "api_key_masked":mask(text(profile,"api_key")),"is_default":yes(profile,"is_default"),"service_type":profiles::kind(profile),
        "reasoning_mode":profile["reasoning_mode"],"reasoning_effort":profile["reasoning_effort"],
        "capabilities":profiles::capabilities(profile),"models":profiles::catalogue(profile)})
}

pub fn preferences(db: &Connection) -> ApiResult {
    let mut prefs = Map::new();
    for (key, value) in [
        ("daily_new_words", "20"),
        ("daily_new_phrases", "10"),
        ("mock_mode", "0"),
        ("auto_speak", "1"),
    ] {
        prefs.insert(key.to_owned(), json!(db::setting(db, key, value)?));
    }
    Ok(Value::Object(prefs))
}

pub fn route(app: &App, method: &str, path: &[&str], body: &Value) -> ApiResult {
    match (method, path) {
        ("GET", []) => db_result(app, |db| {
            let providers: Vec<_> = db::rows(db, "SELECT * FROM ai_providers ORDER BY id", [])?
                .iter()
                .map(payload)
                .collect();
            Ok(json!({"providers":providers,"prefs":preferences(db)?}))
        }),
        ("GET", ["provider-options"]) => Ok(profiles::presets()),
        ("POST", ["provider-capabilities"]) => db_result(app, |db| {
            let saved = body["provider_id"]
                .as_i64()
                .map(|id| selected(db, Some(id)))
                .transpose()?
                .flatten();
            let mut config = body.clone();
            if let Some(profile) = saved.filter(|profile| {
                profile["base_url"] == body["base_url"]
                    && profiles::kind(profile) == text(body, "service_type")
            }) {
                config["models_json"] = profile["models_json"].clone();
            }
            Ok(profiles::capabilities(&config))
        }),
        ("GET", ["codex", "status"]) => {
            let (ok, message) = codex::login_status(Duration::from_secs(10));
            Ok(json!({"ok":ok,"message":message}))
        }
        ("GET", ["codex", "models"]) => {
            Ok(json!({"models":codex::catalogue(),"default_model":codex::default_model()}))
        }
        ("POST", ["providers", "codex"]) => db_result(app, |db| {
            if let Some(profile) = db::one(
                db,
                "SELECT * FROM ai_providers WHERE service_type='codex' ORDER BY id LIMIT 1",
                [],
            )? {
                return Ok(payload(&profile));
            }
            let changed = db.execute("INSERT OR IGNORE INTO ai_providers(name,base_url,api_key,model,is_default,service_type,reasoning_mode,reasoning_effort,models_json)
                VALUES ('Codex（本机 ChatGPT）','','','',0,'codex','auto','','[]')",[])?;
            if changed == 0 {
                return Err(ApiError::new(
                    409,
                    "已有同名服务，请先重命名再添加本机 Codex",
                ));
            }
            Ok(payload(&provider(db, db.last_insert_rowid())?))
        }),
        ("PUT", ["providers", pid, "codex"]) => db_result(app, |db| {
            let pid = id(pid)?;
            let model = text(body, "model").trim();
            let effort = text(body, "reasoning_effort").trim();
            codex::validate(model, effort)?;
            if db.execute("UPDATE ai_providers SET model=?1,reasoning_effort=?2 WHERE id=?3 AND service_type='codex'",
                params![model,effort,pid])?==0 { return Err(ApiError::missing("本机 Codex 服务不存在")); }
            Ok(payload(&provider(db, pid)?))
        }),
        ("POST", ["providers"]) => db_result(app, |db| save(db, body, None)),
        ("PUT", ["providers", pid]) => db_result(app, |db| save(db, body, Some(id(pid)?))),
        ("DELETE", ["providers", pid]) => db_result(app, |db| {
            let pid = id(pid)?;
            let tx = db.transaction()?;
            let existing = provider(&tx, pid)?;
            tx.execute("DELETE FROM ai_providers WHERE id=?1", [pid])?;
            if yes(&existing, "is_default") {
                tx.execute("UPDATE ai_providers SET is_default=1 WHERE id=(SELECT min(id) FROM ai_providers)",[])?;
            }
            tx.commit()?;
            Ok(json!({"ok":true}))
        }),
        ("POST", ["providers", pid, "default"]) => db_result(app, |db| {
            let pid = id(pid)?;
            provider(db, pid)?;
            db.execute("UPDATE ai_providers SET is_default=(id=?1)", [pid])?;
            Ok(json!({"ok":true}))
        }),
        ("POST", ["providers", pid, "models"]) => {
            let pid = id(pid)?;
            let original = db_result(app, |db| provider(db, pid))?;
            let models = ai::refresh(&original)?;
            db_result(app, |db| {
                if db.execute("UPDATE ai_providers SET models_json=?1 WHERE id=?2 AND base_url=?3 AND service_type=?4 AND api_key=?5",
                    params![json!(models).to_string(),pid,text(&original,"base_url"),text(&original,"service_type"),text(&original,"api_key")])?==0 {
                    return Err(ApiError::new(409,"服务配置已更改，请重新刷新"));
                }
                Ok(payload(&provider(db, pid)?))
            })
        }
        ("POST", ["providers", pid, "test"]) => {
            let pid = id(pid)?;
            let profile = db_result(app, |db| provider(db, pid))?;
            let large = profiles::messages(&profile)
                || text(&profile, "model").to_lowercase().starts_with("glm-5")
                || (profile["reasoning_mode"] != "disabled"
                    && profiles::capabilities(&profile)["control"] != "none");
            let session = format!("connection-{pid}-{}", uuid::Uuid::new_v4());
            let result = ai::chat(
                &profile,
                &[json!({"role":"user","content":"Reply with OK."})],
                if large { 32000 } else { 256 },
                &session,
                None,
            );
            Ok(match result {
                Ok(value) => {
                    json!({"ok":true,"message":format!("连接成功：{}",value.chars().take(120).collect::<String>())})
                }
                Err(error) => json!({"ok":false,"message":error.message()}),
            })
        }
        ("PUT", ["prefs"]) => db_result(app, |db| {
            let tx = db.transaction()?;
            for key in ["daily_new_words", "daily_new_phrases"] {
                if let Some(value) = body[key].as_i64() {
                    db::set_setting(&tx, key, &value.clamp(1, 200).to_string())?;
                }
            }
            for key in ["mock_mode", "auto_speak"] {
                if let Some(value) = body[key].as_bool() {
                    db::set_setting(&tx, key, if value { "1" } else { "0" })?;
                }
            }
            tx.commit()?;
            Ok(json!({"ok":true}))
        }),
        _ => Err(ApiError::missing("接口不存在")),
    }
}

fn save(db: &mut Connection, body: &Value, target: Option<i64>) -> ApiResult {
    let tx = db.transaction()?;
    let is_new = target.is_none();
    let mut profile = if let Some(id) = target {
        provider(&tx, id)?
    } else {
        json!({"name":"","base_url":"","api_key":"","service_type":"custom","model":"",
            "reasoning_mode":"auto","reasoning_effort":"","is_default":false,"models_json":"[]"})
    };
    let base = text(body, "base_url").trim();
    let kind = body["service_type"].as_str();
    if (!base.is_empty() && profile["base_url"] != base)
        || kind.is_some_and(|kind| profile["service_type"] != kind)
    {
        profile["models_json"] = json!("[]");
    }
    for key in ["name", "base_url"] {
        let value = text(body, key).trim();
        if !value.is_empty() {
            profile[key] = json!(value);
        }
    }
    let name = text(&profile, "name");
    if name.is_empty() || text(&profile, "base_url").is_empty() {
        return Err(ApiError::bad("名称和 Base URL 不能为空"));
    }
    if name.chars().count() > 60 || text(&profile, "base_url").chars().count() > 200 {
        return Err(ApiError::new(422, "名称或地址超过长度限制"));
    }
    if db::one(
        &tx,
        "SELECT id FROM ai_providers WHERE name=?1 AND (?2 IS NULL OR id!=?2)",
        params![name, target],
    )?
    .is_some()
    {
        return Err(ApiError::bad("同名服务商已存在"));
    }
    let model = text(body, "model").trim();
    profile["model"] = json!(model);
    if is_new && body["reasoning_mode"].is_null() && model.to_lowercase().starts_with("glm-4") {
        profile["reasoning_mode"] = json!("disabled");
    }
    if let Some(value) = kind {
        if !matches!(
            value,
            "custom" | "deepseek" | "opencode_go" | "zhipu" | "anthropic"
        ) {
            return Err(ApiError::new(422, "服务类型无效"));
        }
        profile["service_type"] = json!(value);
    }
    for key in ["reasoning_mode", "reasoning_effort"] {
        if let Some(value) = body[key].as_str() {
            profile[key] = json!(value);
        }
    }
    if profile["reasoning_mode"] == "disabled" {
        profile["reasoning_effort"] = json!("");
    }
    let key = text(body, "api_key").trim();
    if !key.is_empty() && (is_new || !key.contains("****")) {
        profile["api_key"] = json!(key);
    }
    profiles::validate(&profile)?;
    let make_default = yes(body, "is_default")
        || (is_new && db::count(&tx, "SELECT count(*) FROM ai_providers", [])? == 0);
    if make_default {
        tx.execute("UPDATE ai_providers SET is_default=0", [])?;
        profile["is_default"] = json!(true);
    }
    let (name, base, key, model, default, kind, mode, effort, models) = (
        text(&profile, "name"),
        text(&profile, "base_url"),
        text(&profile, "api_key"),
        text(&profile, "model"),
        yes(&profile, "is_default"),
        text(&profile, "service_type"),
        text(&profile, "reasoning_mode"),
        text(&profile, "reasoning_effort"),
        text(&profile, "models_json"),
    );
    let id = if let Some(id) = target {
        tx.execute("UPDATE ai_providers SET name=?1,base_url=?2,api_key=?3,model=?4,is_default=?5,service_type=?6,
            reasoning_mode=?7,reasoning_effort=?8,models_json=?9 WHERE id=?10",params![name,base,key,model,default,kind,mode,effort,models,id])?;
        id
    } else {
        tx.execute("INSERT INTO ai_providers(name,base_url,api_key,model,is_default,service_type,reasoning_mode,reasoning_effort,models_json)
            VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",params![name,base,key,model,default,kind,mode,effort,models])?;
        tx.last_insert_rowid()
    };
    profile["id"] = json!(id);
    tx.commit()?;
    Ok(payload(&profile))
}
