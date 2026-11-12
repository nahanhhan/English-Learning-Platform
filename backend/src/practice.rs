use crate::{
    api::{ApiError, ApiResult, App, Query, db_result, text, yes},
    db, grading, profiles, settings,
};
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use std::sync::Arc;

pub fn route(
    app: &Arc<App>,
    method: &str,
    path: &[&str],
    query: &Query,
    body: &Value,
) -> ApiResult {
    match (method, path) {
        ("POST", ["submit"]) => {
            let value = db_result(app, |db| submit(db, body))?;
            enqueue(
                app,
                value["submission_id"].as_i64().unwrap(),
                body["provider_id"].as_i64(),
            );
            Ok(value)
        }
        ("POST", [id, "regrade"]) => {
            let id = parse_id(id)?;
            let value = db_result(app, |db| {
                let record = submission(db, id)?;
                if matches!(text(&record, "status"), "pending" | "grading") {
                    return Err(ApiError::new(409, "这篇作答正在批改，请等待结果"));
                }
                db.execute("UPDATE submissions SET status='pending' WHERE id=?1", [id])?;
                Ok(json!({"submission_id":id,"status":"pending"}))
            })?;
            enqueue(app, id, body["provider_id"].as_i64());
            Ok(value)
        }
        ("GET", ["history"]) => db_result(app, |db| history(db, query)),
        ("GET", [id]) => db_result(app, |db| result(db, parse_id(id)?)),
        _ => Err(ApiError::missing("接口不存在")),
    }
}

fn parse_id(id: &str) -> ApiResult<i64> {
    id.parse()
        .map_err(|_| ApiError::new(422, "提交编号必须为整数"))
}

fn submission(db: &Connection, id: i64) -> ApiResult {
    db::one(db, "SELECT * FROM submissions WHERE id=?1", [id])?
        .ok_or_else(|| ApiError::missing("提交不存在"))
}

fn submit(db: &Connection, body: &Value) -> ApiResult {
    let content = text(body, "content").trim();
    if content.is_empty() {
        return Err(ApiError::bad("作答内容不能为空"));
    }
    let id = body["question_id"].as_i64();
    let source = if let Some(id) = id.filter(|id| *id != 0) {
        db::one(
            db,
            "SELECT exam_type,q_type,title,prompt,source_text FROM questions WHERE id=?1",
            [id],
        )?
        .ok_or_else(|| ApiError::missing("题目不存在"))?
    } else {
        body.clone()
    };
    db.execute("INSERT INTO submissions(question_id,exam_type,q_type,title,prompt,source_text,content,word_count,status,created_at)
        VALUES (?1,?2,?3,?4,?5,?6,?7,?8,'pending',?9)",params![id,source["exam_type"].as_str().unwrap_or("free"),
        source["q_type"].as_str().unwrap_or("translation"),text(&source,"title"),text(&source,"prompt"),text(&source,"source_text"),
        content,content.split_whitespace().count() as i64,db::now()])?;
    Ok(json!({"submission_id":db.last_insert_rowid(),"status":"pending"}))
}

fn history(db: &Connection, query: &Query) -> ApiResult {
    let exam = query.get("exam_type").filter(|value| !value.is_empty());
    let kind = query.get("q_type").filter(|value| !value.is_empty());
    let page = query.integer("page")?.unwrap_or(1).max(1);
    let size = query.integer("page_size")?.unwrap_or(20).max(1);
    let total = db::count(
        db,
        "SELECT count(*) FROM submissions WHERE (?1 IS NULL OR exam_type=?1) AND (?2 IS NULL OR q_type=?2)",
        params![exam, kind],
    )?;
    let mut items=db::rows(db,"SELECT s.id,s.exam_type,s.q_type,s.title,s.word_count,s.status,s.created_at,g.score,g.full_score
        FROM submissions s LEFT JOIN gradings g ON g.id=(SELECT min(id) FROM gradings WHERE submission_id=s.id)
        WHERE (?1 IS NULL OR s.exam_type=?1) AND (?2 IS NULL OR s.q_type=?2) ORDER BY s.created_at DESC LIMIT ?3 OFFSET ?4",
        params![exam,kind,size,(page-1).saturating_mul(size)])?;
    for row in &mut items {
        if row["full_score"].is_null() {
            row["full_score"] = json!(grading::full_score(
                text(row, "exam_type"),
                text(row, "q_type")
            ));
        }
    }
    Ok(json!({"total":total,"page":page,"items":items}))
}

fn result(db: &Connection, id: i64) -> ApiResult {
    let submission = submission(db, id)?;
    let mut grading = db::one(
        db,
        "SELECT id,provider,model,mock,score,full_score,result_json,error,created_at
        FROM gradings WHERE submission_id=?1 ORDER BY id DESC LIMIT 1",
        [id],
    )?
    .unwrap_or(Value::Null);
    if grading.is_object() {
        let detail = text(&grading, "result_json");
        grading["result"] = if detail.is_empty() {
            Value::Null
        } else {
            serde_json::from_str(detail)?
        };
        grading["mock"] = json!(yes(&grading, "mock"));
        grading.as_object_mut().unwrap().remove("result_json");
    }
    Ok(json!({"submission":submission,"grading":grading}))
}

fn enqueue(app: &Arc<App>, id: i64, provider: Option<i64>) {
    let app = app.clone();
    tokio::task::spawn_blocking(move || {
        if let Err(error) = grade(&app, id, provider) {
            eprintln!("保存练习批改失败：{}", error.message());
            let _ = db_result(&app, |db| {
                db.execute(
                    "UPDATE submissions SET status='failed' WHERE id=?1 AND status='grading'",
                    [id],
                )?;
                Ok(Value::Null)
            });
        }
    });
}

fn grade(app: &App, id: i64, provider: Option<i64>) -> ApiResult {
    let job = db_result(app, |db| {
        if db.execute(
            "UPDATE submissions SET status='grading' WHERE id=?1 AND status='pending'",
            [id],
        )? == 0
        {
            return Ok(Value::Null);
        }
        Ok(
            json!({"submission":submission(db,id)?,"profile":settings::selected(db,provider)?,
            "mock":db::setting(db,"mock_mode","0")?=="1"}),
        )
    })?;
    if job.is_null() {
        return Ok(job);
    }
    let sub = &job["submission"];
    let profile = &job["profile"];
    let full = grading::full_score(text(sub, "exam_type"), text(sub, "q_type"));
    let codex = profiles::kind(profile) == "codex";
    let mock =
        yes(&job, "mock") || (profile.is_object() && text(profile, "api_key").is_empty() && !codex);
    let (result, name, model, mock) = if codex && mock {
        (
            Err(ApiError::bad("已开启模拟批改，请在设置中关闭后使用 Codex")),
            "",
            "",
            false,
        )
    } else if mock {
        (
            Ok(grading::mock(text(sub, "q_type"), full)),
            "模拟批改",
            "mock",
            true,
        )
    } else if profile.is_null() {
        (
            Err(ApiError::bad(
                "尚未配置 AI 服务商，请到「设置」页添加 API Key",
            )),
            "",
            "",
            false,
        )
    } else {
        let model = text(profile, "model");
        (
            grading::grade(sub, profile, &format!("practice-{id}"), full),
            text(profile, "name"),
            if model.is_empty() && codex {
                "Codex 默认模型"
            } else {
                model
            },
            false,
        )
    };
    let (score, detail, error, status) = match result {
        Ok(result) => (
            result["score"].as_f64().unwrap_or(0.0),
            result.to_string(),
            String::new(),
            "done",
        ),
        Err(error) => (0.0, String::new(), error.message().to_owned(), "failed"),
    };
    db_result(app, |db| {
        let tx = db.transaction()?;
        tx.execute("INSERT INTO gradings(submission_id,provider,model,mock,score,full_score,result_json,error,created_at)
            VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",params![id,name,model,mock,score,full,detail,error,db::now()])?;
        tx.execute(
            "UPDATE submissions SET status=?1 WHERE id=?2",
            params![status, id],
        )?;
        tx.commit()?;
        Ok(Value::Null)
    })
}
