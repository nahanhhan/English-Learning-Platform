use crate::{
    ai,
    api::{ApiError, ApiResult, App, Query, db_result, number, text, yes},
    classroom::{self, Library},
    codex, db, grading, profiles, settings,
};
use chrono::{FixedOffset, Utc};
use rand::seq::IndexedRandom;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use std::{
    collections::{BTreeSet, HashMap, HashSet},
    sync::Arc,
    time::Instant,
};

pub fn route(
    app: &Arc<App>,
    method: &str,
    path: &[&str],
    query: &Query,
    body: &Value,
) -> ApiResult {
    match (method, path) {
        ("GET", ["questions"]) => db_result(app, |db| {
            let state = query.get("state").unwrap_or("all");
            if !matches!(state, "all" | "unseen" | "review") {
                return Err(ApiError::new(422, "筛选状态无效"));
            }
            Ok(json!(questions(
                db,
                query.get("topic").unwrap_or(""),
                state,
                query.get("search").unwrap_or("")
            )?))
        }),
        ("GET", ["stats"]) => db_result(app, stats),
        ("POST", ["runs"]) => db_result(app, |db| begin(db, body)),
        ("GET", ["runs", id]) => db_result(app, |db| run_payload(db, &run(db, id)?)),
        ("POST", ["runs", id, "attempts"]) => {
            let result = db_result(app, |db| submit(db, id, body))?;
            if yes(&result, "created") {
                enqueue(app, number(&result, "attempt_id"));
            }
            Ok(json!({"attempt_id":result["attempt_id"],"status":result["status"]}))
        }
        ("GET", ["history"]) => db_result(app, |db| history(db, query)),
        ("PUT", ["questions", id, "review"]) => db_result(app, |db| set_review(db, id, body)),
        ("POST", ["attempts", id, "collect"]) => db_result(app, |db| {
            collect(
                db,
                id.parse().map_err(|_| ApiError::new(422, "作答编号无效"))?,
                body,
            )
        }),
        _ => Err(ApiError::missing("接口不存在")),
    }
}

fn public(data: &Value) -> Value {
    json!({"id":data["id"],"title":data["title"],"topic":data["topic"],"sentences":data["sentences"],"source":data["source"]})
}

fn questions(db: &Connection, topic: &str, state: &str, search: &str) -> ApiResult<Vec<Value>> {
    let mut scores = HashMap::<String, (Option<f64>, Option<f64>)>::new();
    for row in db::rows(
        db,
        "SELECT r.question_id,a.score,a.is_revision FROM short_attempts a
        JOIN short_runs r ON r.id=a.run_id WHERE a.status='done' AND NOT a.mock ORDER BY a.id",
        [],
    )? {
        let score = row["score"].as_f64();
        let pair = scores
            .entry(text(&row, "question_id").to_owned())
            .or_default();
        if !yes(&row, "is_revision") && pair.0.is_none() {
            pair.0 = score;
        }
        pair.1 = score;
    }
    let rows=db::rows(db,"SELECT q.*,p.in_review,p.streak FROM short_questions q LEFT JOIN short_progress p ON p.question_id=q.id
        WHERE (?1='' OR q.topic=?1) ORDER BY q.id",[topic])?;
    let needle = search.to_lowercase();
    let mut result = Vec::new();
    for row in rows {
        let data: Value = serde_json::from_str(text(&row, "data_json"))?;
        let (first, latest) = scores.get(text(&row, "id")).copied().unwrap_or_default();
        let completed = first.is_some();
        let review = yes(&row, "in_review");
        if (state == "unseen" && completed) || (state == "review" && !review) {
            continue;
        }
        if !needle.is_empty()
            && !format!(
                "{}{}",
                text(&row, "title"),
                grading::strings(&data["sentences"]).concat()
            )
            .to_lowercase()
            .contains(&needle)
        {
            continue;
        }
        let mut item = public(&data);
        item["completed"] = json!(completed);
        item["in_review"] = json!(review);
        item["streak"] = json!(number(&row, "streak"));
        item["first_score"] = json!(first);
        item["latest_score"] = json!(latest);
        result.push(item);
    }
    Ok(result)
}

fn stats(db: &mut Connection) -> ApiResult {
    let items = questions(db, "", "all", "")?;
    let done: Vec<_> = items.iter().filter(|item| yes(item, "completed")).collect();
    let topics: BTreeSet<_> = items.iter().map(|item| text(item, "topic")).collect();
    let average = |key: &str| {
        (!done.is_empty()).then(|| {
            grading::rounded(
                done.iter()
                    .filter_map(|item| item[key].as_f64())
                    .sum::<f64>()
                    / done.len() as f64,
            )
        })
    };
    Ok(
        json!({"total":items.len(),"completed":done.len(),"unseen":items.len()-done.len(),
        "review":items.iter().filter(|item|yes(item,"in_review")).count(),"first_average":average("first_score"),
        "latest_average":average("latest_score"),"topics":topics,"performance":done}),
    )
}

fn run(db: &Connection, id: &str) -> ApiResult {
    db::one(db, "SELECT * FROM short_runs WHERE id=?1", [id])?
        .ok_or_else(|| ApiError::missing("练习不存在"))
}

fn begin(db: &Connection, body: &Value) -> ApiResult {
    let mode = body["mode"].as_str().unwrap_or("new");
    if !matches!(mode, "new" | "review") {
        return Err(ApiError::new(422, "练习类型无效"));
    }
    let id = if let Some(id) = body["question_id"].as_str() {
        id.to_owned()
    } else {
        let active: HashSet<_> = db::rows(
            db,
            "SELECT DISTINCT r.question_id FROM short_runs r JOIN short_attempts a ON a.run_id=r.id
            WHERE a.status IN ('pending','grading')",
            [],
        )?
        .iter()
        .map(|row| text(row, "question_id").to_owned())
        .collect();
        let candidates: Vec<_> = questions(
            db,
            text(body, "topic"),
            if mode == "review" { "review" } else { "unseen" },
            "",
        )?
        .into_iter()
        .filter(|item| !active.contains(text(item, "id")))
        .collect();
        text(
            candidates.choose(&mut rand::rng()).ok_or_else(|| {
                ApiError::bad("当前没有可抽取的题目；可从题库选题或继续未完成的练习")
            })?,
            "id",
        )
        .to_owned()
    };
    let q = db::one(
        db,
        "SELECT data_json FROM short_questions WHERE id=?1",
        [&id],
    )?
    .ok_or_else(|| ApiError::missing("题目不存在"))?;
    let run_id = uuid::Uuid::new_v4().to_string();
    db.execute("INSERT INTO short_runs(id,question_id,snapshot,is_review,review_applied,version,created_at)
        VALUES (?1,?2,?3,?4,0,0,?5)",params![run_id,id,text(&q,"data_json"),mode=="review",db::now()])?;
    run_payload(db, &run(db, &run_id)?)
}

fn run_payload(db: &Connection, run: &Value) -> ApiResult {
    let id = text(run, "id");
    let progress = db::one(
        db,
        "SELECT * FROM short_progress WHERE question_id=?1",
        [text(run, "question_id")],
    )?
    .unwrap_or(Value::Null);
    let data: Value = serde_json::from_str(text(run, "snapshot"))?;
    let mut attempts = Vec::new();
    for row in db::rows(
        db,
        "SELECT * FROM short_attempts WHERE run_id=?1 ORDER BY id",
        [id],
    )? {
        let done = row["status"] == "done";
        let result = if done {
            serde_json::from_str::<Value>(text(&row, "result_json"))?
        } else {
            Value::Null
        };
        let mut profile: Value = serde_json::from_str(text(&row, "profile_json"))?;
        if let Some(profile) = profile.as_object_mut() {
            profile.remove("api_key");
        }
        attempts.push(json!({"id":row["id"],"run_id":id,"content":row["content"],"is_revision":yes(&row,"is_revision"),
            "status":row["status"],"score":if done {row["score"].clone()} else {Value::Null},"result":result,
            "profile":profile,"mock":yes(&row,"mock"),"error":row["error"],"created_at":db::iso(text(&row,"created_at"))}));
    }
    let done = attempts.iter().any(|item| item["status"] == "done");
    Ok(
        json!({"id":id,"question":public(&data),"is_review":yes(run,"is_review"),"attempts":attempts,
        "in_review":yes(&progress,"in_review"),"streak":number(&progress,"streak"),
        "reference":if done {data["reference"].clone()}else{Value::Null},
        "training_points":if done {data["training_points"].clone()}else{json!([])}}),
    )
}

fn submit(db: &mut Connection, run_id: &str, body: &Value) -> ApiResult {
    let content = text(body, "content").trim();
    if content.is_empty() {
        return Err(ApiError::bad("请输入完整译文"));
    }
    let request = text(body, "request_id");
    if content.chars().count() > 15000 || request.is_empty() || request.chars().count() > 100 {
        return Err(ApiError::new(422, "译文或请求编号长度不符合要求"));
    }
    let requested = body["provider_id"].as_i64();
    let tx = db.transaction()?;
    if let Some(previous) = db::one(
        &tx,
        "SELECT * FROM short_attempts WHERE request_id=?1",
        [request],
    )? {
        if previous["run_id"] != run_id
            || previous["content"] != content
            || previous["requested_provider_id"].as_i64() != requested
        {
            return Err(ApiError::new(409, "请求编号已被其他作答使用，请重新提交"));
        }
        return Ok(
            json!({"attempt_id":previous["id"],"status":previous["status"],"created":false}),
        );
    }
    run(&tx, run_id)?;
    if db::count(
        &tx,
        "SELECT count(*) FROM short_attempts WHERE run_id=?1 AND status IN ('pending','grading')",
        [run_id],
    )? > 0
    {
        return Err(ApiError::new(409, "这道题正在批改，请等待结果"));
    }
    let profile = settings::selected(&tx, requested)?;
    if profile.is_none() && requested.is_some() {
        return Err(ApiError::missing("所选服务商不存在，请重新选择"));
    }
    let provider = profile.as_ref().and_then(|value| value["id"].as_i64());
    let config = if let Some(profile) = profile {
        json!({"name":profile["name"],"base_url":profile["base_url"],"model":profile["model"],"service_type":profile["service_type"],
            "reasoning_mode":profile["reasoning_mode"],"reasoning_effort":profile["reasoning_effort"],"models_json":profile["models_json"],"provider_id":provider})
    } else {
        json!({})
    };
    let mock = db::setting(&tx, "mock_mode", "0")? == "1";
    let revision = db::count(
        &tx,
        "SELECT count(*) FROM short_attempts WHERE run_id=?1 AND status='done'",
        [run_id],
    )? > 0;
    tx.execute(
        "UPDATE short_runs SET version=version+1 WHERE id=?1",
        [run_id],
    )?;
    tx.execute("INSERT INTO short_attempts(run_id,request_id,content,requested_provider_id,provider_id,profile_json,is_revision,
        status,score,result_json,error,mock,created_at) VALUES (?1,?2,?3,?4,?5,?6,?7,'pending',0,'{}','',?8,?9)",
        params![run_id,request,content,requested,provider,config.to_string(),revision,mock,db::now()])?;
    let id = tx.last_insert_rowid();
    tx.commit()?;
    Ok(json!({"attempt_id":id,"status":"pending","created":true}))
}

fn history(db: &Connection, query: &Query) -> ApiResult {
    let question = query.get("question_id").filter(|value| !value.is_empty());
    let page = query.integer("page")?.unwrap_or(1).max(1);
    let total = db::count(
        db,
        "SELECT count(*) FROM short_runs WHERE (?1 IS NULL OR question_id=?1)",
        [question],
    )?;
    let rows = db::rows(
        db,
        "SELECT * FROM short_runs WHERE (?1 IS NULL OR question_id=?1) ORDER BY created_at DESC LIMIT 20 OFFSET ?2",
        params![question, (page - 1).saturating_mul(20)],
    )?;
    let items = rows
        .iter()
        .map(|row| run_payload(db, row))
        .collect::<ApiResult<Vec<_>>>()?;
    Ok(json!({"total":total,"page":page,"items":items}))
}

fn set_review(db: &mut Connection, id: &str, body: &Value) -> ApiResult {
    if db::one(db, "SELECT id FROM short_questions WHERE id=?1", [id])?.is_none() {
        return Err(ApiError::missing("题目不存在"));
    }
    let enabled = body["enabled"]
        .as_bool()
        .ok_or_else(|| ApiError::new(422, "复习状态无效"))?;
    db.execute("INSERT INTO short_progress(question_id,in_review,streak,last_count_date) VALUES (?1,?2,0,NULL)
        ON CONFLICT(question_id) DO UPDATE SET in_review=excluded.in_review,streak=0,last_count_date=NULL WHERE in_review!=excluded.in_review",
        params![id,enabled])?;
    let streak = db::count(
        db,
        "SELECT streak FROM short_progress WHERE question_id=?1",
        [id],
    )?;
    Ok(json!({"question_id":id,"in_review":enabled,"streak":streak}))
}

fn collect(db: &mut Connection, id: i64, body: &Value) -> ApiResult {
    let tx = db.transaction()?;
    let attempt = db::one(
        &tx,
        "SELECT run_id FROM short_attempts WHERE id=?1 AND status='done'",
        [id],
    )?
    .ok_or_else(|| ApiError::missing("请先完成批改再收藏表达"))?;
    let english = text(body, "english");
    let kind = text(body, "item_type");
    if db::one(
        &tx,
        "SELECT id FROM accumulation_entries WHERE item_type=?1 AND normalized=?2",
        params![kind, db::normalize(english)],
    )?
    .is_some()
    {
        return Ok(json!({"added":0,"skipped":1}));
    }
    let run = run(&tx, text(&attempt, "run_id"))?;
    let data: Value = serde_json::from_str(text(&run, "snapshot"))?;
    let group = if let Some(group) = body["group_id"].as_i64() {
        group
    } else {
        tx.execute(
            "INSERT OR IGNORE INTO accumulation_groups(name) VALUES ('短句翻译积累')",
            [],
        )?;
        db::count(
            &tx,
            "SELECT id FROM accumulation_groups WHERE name='短句翻译积累'",
            [],
        )?
    };
    let source = format!("短句翻译 {} · {}", text(&data, "id"), text(&data, "title"));
    let entry = classroom::save_entry(
        &tx,
        Library::Accumulation,
        &json!({"group_id":group,"item_type":kind,"english":english,"translation":body["translation"],"source":source}),
        None,
    )?;
    tx.commit()?;
    Ok(json!({"added":1,"skipped":0,"entry_id":entry}))
}

fn enqueue(app: &Arc<App>, id: i64) {
    let app = app.clone();
    tokio::task::spawn_blocking(move || {
        if let Err(error) = grade(&app, id) {
            let _ = db_result(&app, |db| {
                db.execute("UPDATE short_attempts SET status='failed',error=?1 WHERE id=?2 AND status='grading'",
                    params![error.message(),id])?;
                Ok(Value::Null)
            });
        }
    });
}

fn grade(app: &App, id: i64) -> ApiResult {
    let job = db_result(app, |db| {
        if db.execute(
            "UPDATE short_attempts SET status='grading' WHERE id=?1 AND status='pending'",
            [id],
        )? == 0
        {
            return Ok(Value::Null);
        }
        let attempt = db::one(db, "SELECT * FROM short_attempts WHERE id=?1", [id])?.unwrap();
        let run = run(db, text(&attempt, "run_id"))?;
        let provider = match attempt["provider_id"].as_i64() {
            Some(pid) => settings::selected(db, Some(pid))?.unwrap_or(Value::Null),
            None => Value::Null,
        };
        let previous=db::one(db,"SELECT content,result_json FROM short_attempts WHERE run_id=?1 AND id<?2 AND status='done'
            ORDER BY id DESC LIMIT 1",params![text(&run,"id"),id])?;
        Ok(json!({"attempt":attempt,"run":run,"provider":provider,"previous":previous}))
    })?;
    if job.is_null() {
        return Ok(job);
    }
    let attempt = &job["attempt"];
    let run = &job["run"];
    let data: Value = serde_json::from_str(text(run, "snapshot"))?;
    let mut profile: Value = serde_json::from_str(text(attempt, "profile_json"))?;
    let mock = yes(attempt, "mock");
    let codex = profiles::kind(&profile) == "codex";
    let result = if mock {
        if codex {
            return Err(ApiError::bad("已开启模拟批改，请在设置中关闭后使用 Codex"));
        }
        mock_result(&data)
    } else {
        let provider = &job["provider"];
        if provider.is_null()
            || (text(provider, "api_key").is_empty() && profiles::kind(provider) != "codex")
        {
            return Err(ApiError::bad(
                "尚未配置有效AI密钥，请在设置页添加后重试；作答已保留",
            ));
        }
        profile["api_key"] = provider["api_key"].clone();
        let previous = &job["previous"];
        let previous = if previous.is_null() {
            Value::Null
        } else {
            json!({"content":previous["content"],"result":serde_json::from_str::<Value>(text(previous,"result_json"))?})
        };
        let body = json!({"原文逐句":data["sentences"],"参考译文":data["reference"],"必译信息":data["key_points"],
            "训练重点":data["training_points"],"考生作答":attempt["content"],"上次作答及点评":previous});
        let messages =
            grading::messages(text(grading::policy(), "short_system"), &body.to_string());
        let deadline = codex.then(|| Instant::now() + codex::TIMEOUT);
        let answer = ai::chat(
            &profile,
            &messages,
            32000,
            &format!("short-{}", text(run, "id")),
            deadline,
        )?;
        validate(&ai::extract_json(&answer)?, &data, text(attempt, "content"))?
    };
    let score = result["score"].as_f64().unwrap_or_default();
    db_result(app, |db| {
        let tx = db.transaction()?;
        tx.execute(
            "UPDATE short_attempts SET status='done',score=?1,result_json=?2 WHERE id=?3",
            params![score, result.to_string(), id],
        )?;
        let applied = db::count(
            &tx,
            "SELECT review_applied FROM short_runs WHERE id=?1",
            [text(run, "id")],
        )?;
        if applied == 0 && !mock {
            apply_progress(&tx, run, score)?;
        }
        tx.execute(
            "UPDATE short_runs SET version=version+1,review_applied=1 WHERE id=?1",
            [text(run, "id")],
        )?;
        tx.commit()?;
        Ok(Value::Null)
    })
}

fn apply_progress(db: &Connection, run: &Value, score: f64) -> ApiResult<()> {
    let id = text(run, "question_id");
    let date = Utc::now()
        .with_timezone(&FixedOffset::east_opt(8 * 3600).unwrap())
        .date_naive()
        .to_string();
    db.execute("INSERT OR IGNORE INTO short_progress(question_id,in_review,streak,last_count_date) VALUES (?1,0,0,NULL)",[id])?;
    if score < 12.0 {
        db.execute("UPDATE short_progress SET in_review=1,streak=0,last_count_date=?1 WHERE question_id=?2",params![date,id])?;
    } else if yes(run, "is_review") {
        db.execute(
            "UPDATE short_progress SET streak=streak+1,in_review=(streak+1<3),last_count_date=?1
            WHERE question_id=?2 AND in_review AND last_count_date IS NOT ?1",
            params![date, id],
        )?;
    }
    Ok(())
}

fn mock_result(data: &Value) -> Value {
    let count = data["sentences"].as_array().map_or(0, Vec::len);
    let comments:Vec<_>=(1..=count).map(|id|json!({"sentence_index":id,"translation":"",
        "comment":"示例点评，请配置真实AI后独立重练。","errors":[],"improvements":[],"suggestion":""})).collect();
    json!({"score":12,"overall_comment":"模拟批改示例，不代表真实评分，也不计入完成或巩固。",
        "dimensions":{"accuracy":4,"language":4,"fluency":4},"sentence_comments":comments,
        "improved_version":data["reference"],"key_notes":[],"resolved_points":[],"remaining_points":[]})
}

fn validate(raw: &Value, data: &Value, content: &str) -> ApiResult {
    let reason = grading::score_reason(raw)?;
    let score = raw["score"]
        .as_f64()
        .filter(|value| (0.0..=15.0).contains(value))
        .ok_or_else(|| ApiError::bad("批改分数不是有效的15分制，请重试"))?;
    if ["overall_comment", "improved_version"]
        .iter()
        .any(|key| text(raw, key).trim().is_empty())
    {
        return Err(ApiError::bad("批改内容不完整，请重试"));
    }
    let n = data["sentences"].as_array().map_or(0, Vec::len);
    let comments = raw["sentence_comments"]
        .as_array()
        .filter(|items| items.len() == n)
        .ok_or_else(|| ApiError::bad("逐句点评不完整，请重试"))?;
    let compact = content.split_whitespace().collect::<String>();
    let mut cleaned = Vec::new();
    for item in comments {
        let index = item["sentence_index"]
            .as_u64()
            .filter(|_| !text(item, "comment").trim().is_empty())
            .ok_or_else(|| ApiError::bad("逐句点评格式不完整，请重试"))?;
        let quote = item
            .get("translation")
            .map_or(Some(""), Value::as_str)
            .filter(|value| compact.contains(&value.split_whitespace().collect::<String>()))
            .ok_or_else(|| ApiError::bad("点评引用的译文未对应原作答，请重试"))?;
        cleaned.push((index,json!({"sentence_index":index,"translation":quote,"comment":item["comment"],
            "suggestion":text(item,"suggestion"),"errors":grading::strings(&item["errors"]),"improvements":grading::strings(&item["improvements"])})));
    }
    cleaned.sort_by_key(|(index, _)| *index);
    if cleaned
        .iter()
        .enumerate()
        .any(|(index, (id, _))| index as u64 + 1 != *id)
    {
        return Err(ApiError::bad("逐句点评编号不完整，请重试"));
    }
    let notes: Vec<_> = raw["key_notes"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|item| item["expr"].is_string())
        .map(|item| grading::project(item, &["expr", "translation", "note", "item_type"]))
        .collect();
    let dims = &raw["dimensions"];
    let dim = |key: &str| grading::rounded(dims[key].as_f64().unwrap_or(0.0).clamp(0.0, 5.0));
    let comments: Vec<_> = cleaned.into_iter().map(|(_, value)| value).collect();
    Ok(
        json!({"score":grading::rounded(score),"overall_comment":raw["overall_comment"],
        "dimensions":{"accuracy":dim("accuracy"),"language":dim("language"),"fluency":dim("fluency")},
        "band":grading::band(score),"rubric_version":grading::policy()["cet6_translation_version"],"score_reason":reason,
        "sentence_comments":comments,"improved_version":raw["improved_version"],"key_notes":notes,
        "resolved_points":grading::strings(&raw["resolved_points"]),"remaining_points":grading::strings(&raw["remaining_points"])}),
    )
}
