use anyhow::{Context, Result, ensure};
use chrono::{Local, Utc};
use rusqlite::{
    Connection, OptionalExtension, Params, TransactionBehavior, params, types::ValueRef,
};
use serde_json::{Map, Value};
use std::{fs, path::Path, time::Duration};

pub fn rows(db: &Connection, sql: &str, values: impl Params) -> rusqlite::Result<Vec<Value>> {
    let mut statement = db.prepare_cached(sql)?;
    let names: Vec<_> = statement
        .column_names()
        .into_iter()
        .map(str::to_owned)
        .collect();
    statement
        .query_map(values, |row| {
            let mut data = Map::new();
            for (index, name) in names.iter().enumerate() {
                let value = match row.get_ref(index)? {
                    ValueRef::Null => Value::Null,
                    ValueRef::Integer(v) => Value::from(v),
                    ValueRef::Real(v) => Value::from(v),
                    ValueRef::Text(v) => Value::from(String::from_utf8_lossy(v).into_owned()),
                    ValueRef::Blob(_) => return Err(rusqlite::Error::InvalidQuery),
                };
                data.insert(name.clone(), value);
            }
            Ok(Value::Object(data))
        })?
        .collect()
}

pub fn one(db: &Connection, sql: &str, values: impl Params) -> rusqlite::Result<Option<Value>> {
    Ok(rows(db, sql, values)?.into_iter().next())
}

pub fn count(db: &Connection, sql: &str, values: impl Params) -> rusqlite::Result<i64> {
    db.query_row(sql, values, |row| row.get(0))
}

pub fn today() -> String {
    Local::now().date_naive().to_string()
}

pub fn now() -> String {
    Local::now().format("%Y-%m-%d %H:%M:%S%.6f").to_string()
}

pub fn utc_now() -> String {
    Utc::now().format("%Y-%m-%d %H:%M:%S%.6f").to_string()
}

pub fn iso(value: &str) -> String {
    value.replace(' ', "T")
}

pub fn setting(db: &Connection, key: &str, default: &str) -> rusqlite::Result<String> {
    Ok(db
        .query_row(
            "SELECT value FROM user_settings WHERE key=?1",
            [key],
            |row| row.get(0),
        )
        .optional()?
        .unwrap_or_else(|| default.to_owned()))
}

pub fn set_setting(db: &Connection, key: &str, value: &str) -> rusqlite::Result<()> {
    db.execute("INSERT INTO user_settings(key,value) VALUES (?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![key, value])?;
    Ok(())
}

pub fn normalize(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

pub fn load_json(dir: &Path, name: &str) -> Result<Value> {
    let path = dir.join(name);
    let content = fs::read(&path).with_context(|| format!("无法读取 {}", path.display()))?;
    serde_json::from_slice(&content).with_context(|| format!("数据格式错误 {}", path.display()))
}

fn add_columns(db: &Connection, table: &str, columns: &[(&str, &str)]) -> Result<bool> {
    let existing = rows(db, &format!("PRAGMA table_info({table})"), [])?;
    let mut added_reasoning_mode = false;
    for (name, definition) in columns {
        if existing.iter().all(|row| row["name"] != *name) {
            db.execute_batch(&format!(
                "ALTER TABLE {table} ADD COLUMN {name} {definition}"
            ))?;
            added_reasoning_mode |= *name == "reasoning_mode";
        }
    }
    Ok(added_reasoning_mode)
}

pub fn open(path: &Path, seeds: &Path) -> Result<Connection> {
    fs::create_dir_all(path)?;
    let mut db = Connection::open(path.join("app.db"))?;
    db.busy_timeout(Duration::from_secs(5))?;
    db.pragma_update(None, "foreign_keys", false)?;
    let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
    tx.execute_batch(include_str!("schema.sql"))?;
    if add_columns(
        &tx,
        "ai_providers",
        &[
            ("service_type", "TEXT DEFAULT 'custom'"),
            ("reasoning_mode", "TEXT DEFAULT 'auto'"),
            ("reasoning_effort", "TEXT DEFAULT ''"),
            ("models_json", "TEXT DEFAULT '[]'"),
        ],
    )? {
        tx.execute(
            "UPDATE ai_providers SET reasoning_mode='disabled' WHERE lower(model) LIKE 'glm-4%'",
            [],
        )?;
    }
    add_columns(
        &tx,
        "srs_cards",
        &[
            ("in_mistake_book", "BOOLEAN DEFAULT 0"),
            ("mistake_consec", "INTEGER DEFAULT 0"),
        ],
    )?;
    seed(&tx, seeds)?;
    tx.execute(
        "UPDATE short_attempts SET status='failed', error='上次批改中断，作答已保存，可手动重试'
        WHERE status IN ('pending','grading')",
        [],
    )?;
    tx.execute(
        "UPDATE submissions SET status='failed' WHERE status IN ('pending','grading')",
        [],
    )?;
    tx.commit()?;
    Ok(db)
}

fn seed(db: &Connection, dir: &Path) -> Result<()> {
    use crate::api::text;
    if count(db, "SELECT EXISTS(SELECT 1 FROM questions)", [])? == 0 {
        for q in load_json(dir, "questions.json")?
            .as_array()
            .context("无效的真题数据")?
        {
            db.execute("INSERT INTO questions(exam_type,year,month,set_no,q_type,title,prompt,source_text,chart_image,source_file,notes)
                VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11)", params![
                text(q,"exam_type"), q["year"].as_i64(), q["month"].as_i64().unwrap_or(0), q["set_no"].as_i64().unwrap_or(1),
                text(q,"q_type"), text(q,"title"), text(q,"prompt"), text(q,"source_text"), text(q,"chart_image"), text(q,"source_file"), text(q,"notes")
            ])?;
        }
    }
    let corrections = load_json(dir, "question_corrections.json")?;
    for item in corrections["corrections"]
        .as_array()
        .context("无效的真题更正数据")?
    {
        let candidates = rows(
            db,
            "SELECT id,source_file FROM questions WHERE exam_type=?1 AND year=?2 AND month=?3 AND set_no=?4 AND q_type=?5",
            params![
                text(item, "exam_type"),
                item["year"].as_i64(),
                item["month"].as_i64(),
                item["set_no"].as_i64(),
                text(item, "q_type")
            ],
        )?;
        if let [current] = candidates.as_slice() {
            if text(current, "source_file").replace('\\', "/")
                != text(item, "source_file").replace('\\', "/")
            {
                continue;
            }
            for (field, change) in item["fields"].as_object().context("无效的题面更正字段")?
            {
                ensure!(
                    ["prompt", "source_text", "chart_image", "notes"].contains(&field.as_str()),
                    "不能修改真题身份字段"
                );
                db.execute(
                    &format!("UPDATE questions SET {field}=?1 WHERE id=?2 AND {field}=?3"),
                    params![
                        text(change, "after"),
                        current["id"].as_i64(),
                        text(change, "before")
                    ],
                )?;
            }
        }
    }
    if count(db, "SELECT EXISTS(SELECT 1 FROM words)", [])? == 0 {
        let data = load_json(dir, "words.json")?;
        let mut insert = db.prepare_cached("INSERT INTO words(book,headword,phonetic_us,phonetic_uk,translation,definition,tags,freq)
            VALUES (?1,?2,?3,'',?4,?5,?6,?7)")?;
        for (book, words) in data.as_object().context("无效的单词书数据")? {
            for word in words.as_array().context("无效的单词列表")? {
                insert.execute(params![
                    book,
                    text(word, "headword"),
                    text(word, "phonetic_us"),
                    text(word, "translation"),
                    text(word, "definition"),
                    text(word, "tags"),
                    word["freq"].as_i64().unwrap_or(0)
                ])?;
            }
        }
    }
    if count(db, "SELECT EXISTS(SELECT 1 FROM phrases)", [])? == 0 {
        let mut insert = db.prepare_cached(
            "INSERT INTO phrases(book,text,translation,note) VALUES ('exam',?1,?2,?3)",
        )?;
        for phrase in load_json(dir, "phrases.json")?
            .as_array()
            .context("无效的短语数据")?
        {
            insert.execute(params![
                text(phrase, "text"),
                text(phrase, "translation"),
                text(phrase, "note")
            ])?;
        }
    }
    for (key, value) in [
        ("daily_new_words", "20"),
        ("daily_new_phrases", "10"),
        ("mock_mode", "0"),
    ] {
        db.execute(
            "INSERT OR IGNORE INTO user_settings(key,value) VALUES (?1,?2)",
            params![key, value],
        )?;
    }
    for file in ["classroom_initial.json", "classroom_how_we_listen.json"] {
        seed_library(db, dir, file, "classroom")?;
    }
    for file in [
        "accumulation_initial.json",
        "accumulation_notes_20261101.json",
        "accumulation_notes_20261102.json",
        "accumulation_notes_20261104.json",
        "accumulation_notes_20261111.json",
    ] {
        seed_library(db, dir, file, "accumulation")?;
    }
    let data = load_json(dir, "short_translations.json")?;
    for question in data["questions"].as_array().context("无效的短句题库")? {
        db.execute("INSERT OR IGNORE INTO short_questions(id,topic,title,data_json,batch) VALUES (?1,?2,?3,?4,?5)",
            params![text(question,"id"), text(question,"topic"), text(question,"title"), question.to_string(), text(&data,"batch")])?;
    }
    Ok(())
}

fn seed_library(db: &Connection, dir: &Path, file: &str, library: &str) -> Result<()> {
    use crate::api::text;
    let data = load_json(dir, file)?;
    let version = text(&data, "version");
    if count(
        db,
        "SELECT EXISTS(SELECT 1 FROM user_settings WHERE key=?1)",
        [version],
    )? != 0
    {
        return Ok(());
    }
    let groups = format!("{library}_groups");
    let entries = format!("{library}_entries");
    let insert = format!("INSERT OR IGNORE INTO {entries}(group_id,item_type,english,normalized,translation,source,in_mistake_book,mistake_consec,completed)
        VALUES (?1,?2,?3,?4,?5,?6,0,0,0)");
    for group in data["groups"].as_array().context("无效的词库分组")? {
        let name = text(group, "name");
        db.execute(
            &format!("INSERT OR IGNORE INTO {groups}(name) VALUES (?1)"),
            [name],
        )?;
        let id = count(
            db,
            &format!("SELECT id FROM {groups} WHERE name=?1"),
            [name],
        )?;
        if library == "accumulation" {
            for entry in group["entries"].as_array().context("无效的积累词条")? {
                let kind = text(entry, "item_type");
                let english = text(entry, "english").trim();
                let normalized = normalize(english);
                if count(
                    db,
                    "SELECT EXISTS(SELECT 1 FROM accumulation_entries WHERE item_type=?1 AND normalized=?2)",
                    params![kind, normalized],
                )? == 0
                {
                    db.execute(
                        &insert,
                        params![
                            id,
                            kind,
                            english,
                            normalized,
                            text(entry, "translation").trim(),
                            text(entry, "source").trim()
                        ],
                    )?;
                }
            }
        } else {
            for (key, kind) in [("words", "word"), ("phrases", "phrase")] {
                for entry in group[key].as_array().context("无效的课内词条")? {
                    let english = entry[0].as_str().context("无效的英文词条")?.trim();
                    let translation = entry[1].as_str().context("无效的中文释义")?.trim();
                    db.execute(
                        &insert,
                        params![
                            id,
                            kind,
                            english,
                            normalize(english),
                            translation,
                            text(group, "source").trim()
                        ],
                    )?;
                }
            }
        }
    }
    set_setting(db, version, "1")?;
    Ok(())
}
