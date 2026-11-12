use crate::{
    api::{ApiError, ApiResult, Query, number, text},
    db,
};
use chrono::{Days, Local};
use rusqlite::{Connection, params};
use serde_json::{Map, Value, json};
use std::{collections::HashSet, path::Path};

fn attach_chart(row: &mut Value, data: &Path) {
    let image = text(row, "chart_image");
    let Some(name) = image.strip_prefix("charts/") else {
        return;
    };
    if name
        .split(['/', '\\'])
        .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return;
    }
    let vector = Path::new(name)
        .with_extension("svg")
        .to_string_lossy()
        .replace('\\', "/");
    let original = format!("originals/{name}");
    for (key, path) in [
        ("chart_display_image", vector),
        ("chart_original_image", original),
    ] {
        let relative = format!("charts/{path}");
        if data.join(&relative).is_file() {
            row[key] = json!(relative);
        }
    }
}

pub fn list(db: &Connection, query: &Query, data: &Path) -> ApiResult {
    let exam_type = query.get("exam_type").filter(|value| !value.is_empty());
    let question_type = query.get("q_type").filter(|value| !value.is_empty());
    let year = query.integer("year")?.filter(|year| *year != 0);
    let mut filters = Vec::new();
    let mut values = Vec::new();
    if let Some(exam_type) = exam_type {
        filters.push("exam_type=?");
        values.push(rusqlite::types::Value::from(exam_type.to_owned()));
    }
    if let Some(question_type) = question_type {
        filters.push("q_type=?");
        values.push(rusqlite::types::Value::from(question_type.to_owned()));
    }
    if let Some(year) = year {
        filters.push("year=?");
        values.push(rusqlite::types::Value::from(year));
    }
    let where_clause = if filters.is_empty() {
        String::new()
    } else {
        format!("WHERE {}", filters.join(" AND "))
    };
    let sql = format!(
        "SELECT q.id,exam_type,year,month,set_no,q_type,title,prompt,source_text,chart_image,notes,
        (SELECT count(*) FROM submissions s WHERE s.question_id=q.id) practice_count
        FROM questions q {where_clause} ORDER BY year DESC, month DESC, set_no"
    );
    let mut result = db::rows(db, &sql, rusqlite::params_from_iter(values))?;
    for row in &mut result {
        attach_chart(row, data);
    }
    Ok(json!(result))
}

pub fn detail(db: &Connection, id: &str, data: &Path) -> ApiResult {
    let id = id
        .parse::<i64>()
        .map_err(|_| ApiError::new(422, "题目编号必须为整数"))?;
    let mut row = db::one(
        db,
        "SELECT id,exam_type,year,month,set_no,q_type,title,prompt,source_text,chart_image,notes
        FROM questions WHERE id=?1",
        [id],
    )?
    .ok_or_else(|| ApiError::missing("题目不存在"))?;
    attach_chart(&mut row, data);
    Ok(row)
}

pub fn meta(db: &mut Connection) -> ApiResult {
    let mut result = Map::new();
    for exam in ["cet6", "ky2"] {
        let years: Vec<_> = db::rows(
            db,
            "SELECT DISTINCT year FROM questions WHERE exam_type=?1 ORDER BY year DESC",
            [exam],
        )?
        .into_iter()
        .map(|row| number(&row, "year"))
        .collect();
        let types: Vec<_> = db::rows(
            db,
            "SELECT DISTINCT q_type FROM questions WHERE exam_type=?1",
            [exam],
        )?
        .into_iter()
        .map(|row| text(&row, "q_type").to_owned())
        .collect();
        result.insert(exam.to_owned(), json!({"years":years,"q_types":types}));
    }
    Ok(Value::Object(result))
}

pub fn books(db: &Connection, kind: &str) -> ApiResult<Vec<Value>> {
    let table = if kind == "word" { "words" } else { "phrases" };
    let sql = format!(
        "SELECT w.book,w.total AS total_items,count(s.id) AS cards,
        count(*) FILTER (WHERE s.status='new') AS new,
        count(*) FILTER (WHERE s.status='learning') AS learning,
        count(*) FILTER (WHERE s.status='review') AS review,
        count(*) FILTER (WHERE s.status!='new') AS started,
        count(*) FILTER (WHERE s.status='review' AND s.interval_days>=30) AS mastered,
        count(*) FILTER (WHERE s.starred) AS starred,
        count(*) FILTER (WHERE s.status!='new' AND s.due<=?2) AS due_now
        FROM (SELECT book,count(*) total FROM {table} GROUP BY book) w
        LEFT JOIN srs_cards s ON s.book=w.book AND s.item_type=?1 GROUP BY w.book ORDER BY w.book"
    );
    Ok(db::rows(db, &sql, params![kind, db::today()])?)
}

pub fn dashboard(db: &mut Connection) -> ApiResult {
    let date = Local::now().date_naive();
    let today = date.to_string();
    let dates: HashSet<_> = db::rows(db, "SELECT date(reviewed_at) day FROM review_logs UNION SELECT date(created_at) FROM submissions", [])?
        .into_iter().map(|row| text(&row, "day").to_owned()).collect();
    let mut cur = if dates.contains(&today) {
        Some(date)
    } else {
        date.checked_sub_days(Days::new(1))
    };
    let mut streak = 0;
    while let Some(day) = cur.filter(|day| dates.contains(&day.to_string())) {
        streak += 1;
        cur = day.checked_sub_days(Days::new(1));
    }
    let reviews = db::count(
        db,
        "SELECT count(*) FROM review_logs WHERE date(reviewed_at)=?1",
        [&today],
    )?;
    let new = db::count(
        db,
        "SELECT count(*) FROM srs_cards WHERE added_at=?1 AND status!='new'",
        [&today],
    )?;
    let practices = db::count(
        db,
        "SELECT count(*) FROM submissions WHERE date(created_at)=?1",
        [&today],
    )?;
    let trend = db::rows(db, "SELECT date(g.created_at) date,s.exam_type,s.q_type,g.score,g.full_score,
        coalesce(nullif(s.title,''),'自由练习') title FROM gradings g JOIN submissions s ON s.id=g.submission_id
        WHERE g.error='' ORDER BY g.created_at", [])?;
    let recent = db::rows(
        db,
        "SELECT s.id,coalesce(nullif(s.title,''),'自由练习') title,s.q_type,s.exam_type,
        s.status,g.score,g.full_score,s.created_at FROM submissions s
        LEFT JOIN gradings g ON g.id=(SELECT max(id) FROM gradings WHERE submission_id=s.id)
        ORDER BY s.created_at DESC LIMIT 8",
        [],
    )?;
    let practice_counts: Map<_, _> = db::rows(
        db,
        "SELECT q_type,count(*) total FROM submissions GROUP BY q_type",
        [],
    )?
    .into_iter()
    .map(|row| (text(&row, "q_type").to_owned(), row["total"].clone()))
    .collect();
    let due = |kind| {
        db::count(
            db,
            "SELECT count(*) FROM srs_cards WHERE item_type=?1 AND status!='new' AND due<=?2",
            params![kind, &today],
        )
    };
    Ok(
        json!({"streak":streak,"today":{"reviews":reviews,"new_words":new,"practices":practices},
        "due":{"words":due("word")?,"phrases":due("phrase")?},"word_books":books(db,"word")?,
        "phrase_books":books(db,"phrase")?,"trend":trend,"practice_counts":practice_counts,"recent":recent}),
    )
}
