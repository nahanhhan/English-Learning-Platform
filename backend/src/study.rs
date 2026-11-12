use crate::{
    api::{ApiError, ApiResult, Query, number, text, yes},
    db, dictionary, questions,
};
use chrono::{Days, Local};
use rand::seq::SliceRandom;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use std::{collections::HashSet, path::Path};

#[derive(Clone, Copy)]
struct BookKind(&'static str);

impl BookKind {
    fn table(self) -> &'static str {
        if self.0 == "word" { "words" } else { "phrases" }
    }
}

pub fn route(
    db: &mut Connection,
    data: &Path,
    method: &str,
    path: &[&str],
    query: &Query,
    body: &Value,
) -> ApiResult {
    let phrase = path[0] == "phrases";
    let kind = BookKind(if phrase || query.get("item_type") == Some("phrase") {
        "phrase"
    } else {
        "word"
    });
    let custom_kind = BookKind(if phrase { "phrase" } else { "word" });
    let book = || {
        query
            .get("book")
            .or_else(|| phrase.then_some("exam"))
            .ok_or_else(|| ApiError::new(422, "请选择词书"))
    };
    match (method, &path[1..]) {
        ("GET", ["books"]) => Ok(json!(questions::books(db, kind.0)?)),
        ("GET", ["queue"]) => queue(
            db,
            data,
            kind,
            book()?,
            query.get("source").unwrap_or("normal"),
        ),
        ("GET", ["mistakes"]) => Ok(json!(mistakes(db, data, kind, book()?)?)),
        ("GET", ["browse"]) => browse(db, data, kind, book()?, query),
        ("GET", ["quiz"]) => quiz(db, data, kind, book()?, query),
        ("POST", ["answer"]) => answer(db, data, number(body, "card_id"), text(body, "rating")),
        ("POST", ["star"]) => star(db, number(body, "card_id")),
        ("POST", ["custom"]) => add_custom(db, custom_kind, body),
        ("DELETE", ["custom", id]) => delete_custom(db, custom_kind, id),
        _ => Err(ApiError::missing("接口不存在")),
    }
}

fn payload(db: &Connection, data: &Path, card: &Value) -> ApiResult {
    let kind = BookKind(if card["item_type"] == "word" {
        "word"
    } else {
        "phrase"
    });
    let mut result = json!({
        "card_id":card["id"], "status":card["status"], "due":card["due"], "interval":card["interval_days"],
        "reps":card["reps"], "starred":yes(card,"starred"),
        "in_mistake_book":yes(card,"in_mistake_book"), "mistake_consec":number(card,"mistake_consec"),
    });
    let item = db::one(
        db,
        &format!("SELECT * FROM {} WHERE id=?1", kind.table()),
        [number(card, "item_id")],
    )?;
    if let Some(item) = item {
        result["id"] = item["id"].clone();
        result["book"] = item["book"].clone();
        let translation = text(&item, "translation");
        result["translation"] = json!(translation.replace("\\n", "\n"));
        if kind.0 == "word" {
            let english = text(&item, "headword");
            let definition = text(&item, "definition");
            let mut ipa = dictionary::ipa(data, english);
            if ipa.is_empty() && item["book"] == "custom" {
                ipa = text(&item, "phonetic_us").to_owned();
            }
            result["headword"] = json!(english);
            result["phonetic_us"] = json!(ipa);
            result["part_of_speech"] =
                json!(dictionary::parts(data, english, translation, definition));
            result["definition"] = json!(definition.replace("\\n", "\n"));
        } else {
            result["text"] = item["text"].clone();
            result["note"] = json!(text(&item, "note").replace("\\n", "\n"));
        }
    }
    Ok(result)
}

fn cards(
    db: &Connection,
    data: &Path,
    sql: &str,
    values: impl rusqlite::Params,
) -> ApiResult<Vec<Value>> {
    db::rows(db, sql, values)?
        .iter()
        .map(|row| payload(db, data, row))
        .collect()
}

fn first_line(translation: &str) -> String {
    translation
        .replace("\\n", "\n")
        .split('\n')
        .next()
        .unwrap_or("")
        .chars()
        .take(40)
        .collect()
}

fn choices(
    db: &Connection,
    kind: BookKind,
    book: &str,
    batches: [&mut [Value]; 2],
) -> ApiResult<()> {
    if batches.iter().all(|batch| batch.is_empty()) {
        return Ok(());
    }
    let pool: HashSet<_> = db::rows(
        db,
        &format!("SELECT translation FROM {} WHERE book=?1", kind.table()),
        [book],
    )?
    .into_iter()
    .map(|row| first_line(text(&row, "translation")))
    .filter(|value| !value.is_empty())
    .collect();
    let pool: Vec<_> = pool.iter().collect();
    let mut rng = rand::rng();
    for card in batches.into_iter().flatten() {
        let answer = first_line(text(card, "translation"));
        let mut candidates = pool
            .iter()
            .copied()
            .filter(|value| ***value != answer)
            .collect::<Vec<_>>();
        candidates.shuffle(&mut rng);
        candidates.truncate(3);
        candidates.push(&answer);
        candidates.shuffle(&mut rng);
        card["options"] = json!(candidates);
        card["answer"] = json!(answer);
    }
    Ok(())
}

fn mistakes(db: &Connection, data: &Path, kind: BookKind, book: &str) -> ApiResult<Vec<Value>> {
    cards(
        db,
        data,
        "SELECT * FROM srs_cards WHERE item_type=?1 AND book=?2 AND in_mistake_book ORDER BY due,id",
        params![kind.0, book],
    )
}

fn add_card(db: &Connection, kind: BookKind, id: i64, book: &str, today: &str) -> ApiResult<()> {
    db.execute("INSERT INTO srs_cards(item_type,item_id,book,status,ease,interval_days,due,reps,lapses,starred,in_mistake_book,mistake_consec,added_at)
        VALUES (?1,?2,?3,'new',2.5,0,?4,0,0,0,0,0,?4)", params![kind.0,id,book,today])?;
    Ok(())
}

fn queue(db: &mut Connection, data: &Path, kind: BookKind, book: &str, source: &str) -> ApiResult {
    if source == "mistake" {
        let mut review = mistakes(db, data, kind, book)?;
        choices(db, kind, book, [&mut review, &mut []])?;
        return Ok(
            json!({"review":review,"new":[],"counts":{"review":review.len(),"new":0,"quota_left":0,"added_today":0,"source":"mistake"}}),
        );
    }
    let today = db::today();
    let tx = db.transaction()?;
    let key = if kind.0 == "phrase" {
        "daily_new_phrases"
    } else {
        "daily_new_words"
    };
    let quota = db::setting(&tx, key, "20")?.parse::<i64>().unwrap_or(20);
    let added = db::count(
        &tx,
        "SELECT count(*) FROM srs_cards WHERE item_type=?1 AND book=?2 AND added_at=?3",
        params![kind.0, book, today],
    )?;
    let pending = db::count(
        &tx,
        "SELECT count(*) FROM srs_cards WHERE item_type=?1 AND book=?2 AND added_at=?3 AND status='new'",
        params![kind.0, book, today],
    )?;
    let remain = (quota - added).max(0) - pending;
    if remain > 0 {
        let order = if kind.0 == "word" {
            "i.freq DESC,i.headword"
        } else {
            "i.id"
        };
        let query = format!(
            "SELECT id FROM {} i WHERE i.book=?2 AND NOT EXISTS (
            SELECT 1 FROM srs_cards s WHERE s.item_id=i.id AND s.item_type=?1 AND s.book=?2)
            ORDER BY {order} LIMIT ?3",
            kind.table()
        );
        for row in db::rows(&tx, &query, params![kind.0, book, remain])? {
            add_card(&tx, kind, number(&row, "id"), book, &today)?;
        }
    }
    let mut review = cards(
        &tx,
        data,
        "SELECT * FROM srs_cards WHERE item_type=?1 AND book=?2 AND status!='new' AND due<=?3 ORDER BY due",
        params![kind.0, book, today],
    )?;
    let mut new = cards(
        &tx,
        data,
        "SELECT * FROM srs_cards WHERE item_type=?1 AND book=?2 AND status='new' AND added_at=?3 ORDER BY id",
        params![kind.0, book, today],
    )?;
    tx.commit()?;
    choices(db, kind, book, [&mut review, &mut new])?;
    Ok(
        json!({"review":review,"new":new,"counts":{"review":review.len(),"new":new.len(),
        "quota_left":remain.max(0),"added_today":added,"source":"normal"}}),
    )
}

fn answer(db: &mut Connection, data: &Path, id: i64, rating: &str) -> ApiResult {
    let tx = db.transaction()?;
    let card = db::one(&tx, "SELECT * FROM srs_cards WHERE id=?1", [id])?
        .ok_or_else(|| ApiError::bad("卡片不存在"))?;
    let ease = card["ease"]
        .as_f64()
        .filter(|value| *value != 0.0)
        .unwrap_or(2.5);
    let last = card["interval_days"].as_f64().unwrap_or_default();
    let new = card["status"] == "new" || last == 0.0;
    let (ease, interval, status, lapse) = match rating {
        "again" => ((ease - 0.2).max(1.3), 0.0, "learning", 1),
        "hard" if new => ((ease - 0.05).max(1.3), 0.5, "learning", 0),
        "hard" => ((ease - 0.05).max(1.3), (last * 1.2).max(1.0), "review", 0),
        "good" if new => (ease, 1.0, "learning", 0),
        "good" if last < 3.0 => (ease, 3.0, "review", 0),
        "good" => (ease, last * ease, "review", 0),
        _ => return Err(ApiError::bad("无效评分")),
    };
    let today = Local::now().date_naive();
    let due = today
        .checked_add_days(Days::new(interval.round_ties_even().max(0.0) as u64))
        .ok_or_else(|| ApiError::bad("复习间隔超出有效范围"))?
        .to_string();
    let (mistake, consecutive) = if rating != "good" {
        (true, 0)
    } else if yes(&card, "in_mistake_book") && number(&card, "mistake_consec") + 1 < 3 {
        (true, number(&card, "mistake_consec") + 1)
    } else {
        (false, 0)
    };
    let now = db::now();
    tx.execute("UPDATE srs_cards SET ease=?1,interval_days=?2,status=?3,lapses=lapses+?4,due=?5,reps=reps+1,
        in_mistake_book=?6,mistake_consec=?7,last_review_at=?8 WHERE id=?9",
        params![ease,interval,status,lapse,due,mistake,consecutive,now,id])?;
    tx.execute("INSERT INTO review_logs(card_id,item_type,rating,last_interval,next_interval,reviewed_at) VALUES (?1,?2,?3,?4,?5,?6)",
        params![id,text(&card,"item_type"),rating,last,interval,now])?;
    let result = payload(
        &tx,
        data,
        &db::one(&tx, "SELECT * FROM srs_cards WHERE id=?1", [id])?.unwrap(),
    )?;
    tx.commit()?;
    Ok(result)
}

fn star(db: &Connection, id: i64) -> ApiResult {
    let value = db::one(
        db,
        "UPDATE srs_cards SET starred=NOT starred WHERE id=?1 RETURNING starred",
        [id],
    )?
    .ok_or_else(|| ApiError::missing("卡片不存在"))?;
    Ok(json!({"card_id":id,"starred":yes(&value,"starred")}))
}

fn browse(db: &Connection, data: &Path, kind: BookKind, book: &str, query: &Query) -> ApiResult {
    let status = query.get("status").unwrap_or("all");
    let where_clause = match status {
        "new" => " AND status='new'",
        "learning" => " AND status='learning'",
        "review" => " AND status='review'",
        "mastered" => " AND status='review' AND interval_days>=30",
        _ => "",
    };
    let filter = format!(
        "FROM srs_cards WHERE item_type=?1 AND book=?2 AND (?3 IS NULL OR starred=?3){where_clause}"
    );
    let starred = query.get("starred").map(|_| query.flag("starred"));
    let page = query.integer("page")?.unwrap_or(1).max(1);
    let size = query.integer("page_size")?.unwrap_or(30).max(1);
    let mut total = db::count(
        db,
        &format!("SELECT count(*) {filter}"),
        params![kind.0, book, starred],
    )?;
    let mut items = cards(
        db,
        data,
        &format!("SELECT * {filter} ORDER BY id DESC LIMIT ?4 OFFSET ?5"),
        params![kind.0, book, starred, size, (page - 1).saturating_mul(size)],
    )?;
    if let Some(search) = query.get("search").filter(|value| !value.is_empty()) {
        let needle = search.to_lowercase();
        items.retain(|item| {
            text(item, "headword").to_lowercase().contains(&needle)
                || text(item, "text").to_lowercase().contains(&needle)
                || text(item, "translation").contains(search)
        });
        total = items.len() as i64;
    }
    Ok(json!({"total":total,"page":page,"items":items}))
}

fn quiz(db: &Connection, data: &Path, kind: BookKind, book: &str, query: &Query) -> ApiResult {
    let count = query.integer("count")?.unwrap_or(10).max(0);
    let mut items = cards(
        db,
        data,
        "SELECT * FROM srs_cards WHERE item_type=?1 AND book=?2 ORDER BY (status='new'),random() LIMIT ?3",
        params![kind.0, book, count],
    )?;
    choices(db, kind, book, [&mut items, &mut []])?;
    let result: Vec<_> = items.into_iter().map(|item| json!({
        "card_id":item["card_id"],"front":item.get("headword").unwrap_or(&item["text"]),
        "phonetic":text(&item,"phonetic_us"),"part_of_speech":text(&item,"part_of_speech"),
        "answer":item["answer"],"options":item["options"],"full_translation":item["translation"],
        "direction":query.get("direction").unwrap_or("e2c"),
    })).collect();
    Ok(json!(result))
}

fn add_custom(db: &mut Connection, kind: BookKind, body: &Value) -> ApiResult {
    let word = kind.0 == "word";
    let english = text(body, if word { "headword" } else { "text" }).trim();
    let meaning = text(body, "translation").trim();
    if english.is_empty() || meaning.is_empty() {
        return Err(ApiError::bad(if word {
            "单词和释义不能为空"
        } else {
            "短语和释义不能为空"
        }));
    }
    let tx = db.transaction()?;
    if word {
        tx.execute("INSERT INTO words(book,headword,translation,phonetic_us,phonetic_uk,definition,tags,freq)
            VALUES ('custom',?1,?2,?3,'',?4,'custom',99)",params![english,meaning,text(body,"phonetic_us").trim(),text(body,"definition").trim()])?;
    } else {
        tx.execute(
            "INSERT INTO phrases(book,text,translation,note) VALUES ('custom',?1,?2,?3)",
            params![english, meaning, text(body, "note").trim()],
        )?;
    }
    let id = tx.last_insert_rowid();
    add_card(&tx, kind, id, "custom", &db::today())?;
    tx.commit()?;
    Ok(json!({"id":id}))
}

fn delete_custom(db: &mut Connection, kind: BookKind, id: &str) -> ApiResult {
    let id = id
        .parse::<i64>()
        .map_err(|_| ApiError::new(422, "无效的词条编号"))?;
    let tx = db.transaction()?;
    if tx.execute(
        &format!("DELETE FROM {} WHERE id=?1 AND book='custom'", kind.table()),
        [id],
    )? == 0
    {
        return Err(ApiError::missing("词条不存在或不可删除"));
    }
    tx.execute(
        "DELETE FROM srs_cards WHERE item_type=?1 AND item_id=?2",
        params![kind.0, id],
    )?;
    tx.commit()?;
    Ok(json!({"ok":true}))
}
