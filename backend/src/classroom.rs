use crate::{
    api::{ApiError, ApiResult, Query, number, text, yes},
    db, dictionary,
};
use rand::seq::SliceRandom;
use regex::Regex;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use std::{
    cmp::Ordering,
    collections::{HashMap, HashSet},
    path::Path,
    sync::OnceLock,
};

#[derive(Clone, Copy)]
pub enum Library {
    Classroom,
    Accumulation,
}

impl Library {
    fn name(self) -> &'static str {
        match self {
            Self::Classroom => "classroom",
            Self::Accumulation => "accumulation",
        }
    }
    fn accumulated(self) -> bool {
        matches!(self, Self::Accumulation)
    }
    fn table(self, suffix: &str) -> String {
        format!("{}_{suffix}", self.name())
    }
}

fn id(value: &str) -> ApiResult<i64> {
    value
        .parse()
        .map_err(|_| ApiError::new(422, "编号必须为整数"))
}

fn scope(group: Option<i64>, kind: &str, source: &str) -> ApiResult<String> {
    if !matches!(kind, "all" | "word" | "phrase") || !matches!(source, "normal" | "mistake") {
        return Err(ApiError::new(422, "练习范围无效"));
    }
    Ok(format!(
        "{}:{kind}:{source}",
        group
            .filter(|id| *id != 0)
            .map(|id| id.to_string())
            .unwrap_or_else(|| "all".into())
    ))
}

pub fn route(
    db: &mut Connection,
    data: &Path,
    method: &str,
    path: &[&str],
    query: &Query,
    body: &Value,
) -> ApiResult {
    let library = if path[0] == "accumulation" {
        Library::Accumulation
    } else {
        Library::Classroom
    };
    let groups = library.table("groups");
    let entries = library.table("entries");
    let sessions = library.table("sessions");
    match (method, &path[1..]) {
        ("GET", ["groups"]) => Ok(json!(db::rows(db, &format!("SELECT g.id,g.name,count(e.id) total,
            count(*) FILTER(WHERE e.in_mistake_book) mistakes, count(*) FILTER(WHERE e.item_type='word') words,
            count(*) FILTER(WHERE e.item_type='phrase') phrases,
            count(*) FILTER(WHERE e.in_mistake_book AND e.item_type='word') word_mistakes,
            count(*) FILTER(WHERE e.in_mistake_book AND e.item_type='phrase') phrase_mistakes
            FROM {groups} g LEFT JOIN {entries} e ON e.group_id=g.id GROUP BY g.id ORDER BY g.id"), [])?)),
        ("POST", ["groups"]) => save_group(db, &groups, body, None),
        ("PUT", ["groups", group]) => save_group(db, &groups, body, Some(id(group)?)),
        ("DELETE", ["groups", group]) => {
            let group = id(group)?;
            let tx = db.transaction()?;
            if tx.execute(&format!("DELETE FROM {groups} WHERE id=?1"), [group])? == 0 {
                return Err(ApiError::missing("分组不存在"));
            }
            if library.accumulated() {
                tx.execute("DELETE FROM accumulation_review_logs WHERE entry_id IN
                    (SELECT id FROM accumulation_entries WHERE group_id=?1)",[group])?;
            }
            tx.execute(&format!("DELETE FROM {entries} WHERE group_id=?1"),[group])?;
            tx.commit()?;
            Ok(json!({"ok":true}))
        }
        ("GET", ["entries"]) => {
            let page = query.integer("page")?.unwrap_or(1).max(1);
            let size = query.integer("page_size")?.unwrap_or(30).clamp(1,100);
            let group = query.integer("group_id")?;
            let kind = query.get("item_type").unwrap_or("all");
            scope(group,kind,"normal")?;
            let term = query.get("search").unwrap_or("").trim();
            let sql = format!("FROM {entries} WHERE (?1 IS NULL OR group_id=?1) AND (?2='all' OR item_type=?2)
                AND (NOT ?3 OR in_mistake_book) AND (?4='' OR instr(lower(english), lower(?4)) OR instr(lower(translation),lower(?4)))");
            let total = db::count(db,&format!("SELECT count(*) {sql}"),params![group,kind,query.flag("mistakes"),term])?;
            let page_rows = db::rows(db,&format!("SELECT * {sql} ORDER BY id LIMIT ?5 OFFSET ?6"),
                params![group,kind,query.flag("mistakes"),term,size,(page-1).saturating_mul(size)])?;
            let result = page_rows.into_iter().map(|row| entry_payload(db,data,library,row)).collect::<ApiResult<Vec<_>>>()?;
            Ok(json!({"total":total,"page":page,"items":result}))
        }
        ("POST", ["entries"]) | ("PUT", ["entries", _]) => {
            let entry_id = path.get(2).map(|value| id(value)).transpose()?;
            let entry = save_entry(db,library,body,entry_id)?;
            let row = db::one(db,&format!("SELECT * FROM {entries} WHERE id=?1"),[entry])?.unwrap();
            entry_payload(db,data,library,row)
        }
        ("DELETE", ["entries", entry]) => {
            let entry = id(entry)?;
            let tx = db.transaction()?;
            if tx.execute(&format!("DELETE FROM {entries} WHERE id=?1"),[entry])? == 0 {
                return Err(ApiError::missing("词条不存在"));
            }
            if library.accumulated() { tx.execute("DELETE FROM accumulation_review_logs WHERE entry_id=?1",[entry])?; }
            tx.commit()?;
            Ok(json!({"ok":true}))
        }
        ("POST", ["imports", "confirm"]) => {
            let rows = body["rows"].as_array().filter(|rows| rows.len() <= 5000)
                .ok_or_else(|| ApiError::new(422,"导入词条格式无效或超过 5000 条"))?;
            let tx = db.transaction()?;
            let mut added = 0;
            let mut skipped = 0;
            for row in rows {
                match save_entry(&tx,library,row,None) {
                    Ok(_) => added += 1,
                    Err(error) if error.is_conflict() => skipped += 1,
                    Err(error) => return Err(error),
                }
            }
            tx.commit()?;
            Ok(json!({"added":added,"skipped":skipped}))
        }
        ("POST", ["imports", "text"]) => {
            let raw = text(body,"text");
            Ok(json!({"raw_text":raw,"rows":parse_text(raw)}))
        }
        ("GET", ["sessions", "current"]) => {
            let key = scope(query.integer("group_id")?,query.get("item_type").unwrap_or("all"),query.get("source").unwrap_or("normal"))?;
            let tx = db.transaction()?;
            let Some(row) = db::one(&tx,&format!("SELECT id FROM {sessions} WHERE scope=?1"),[key])? else { return Ok(Value::Null); };
            let result = session_payload(&tx,data,library,number(&row,"id"))?;
            tx.commit()?;
            Ok(result)
        }
        ("POST", ["sessions"]) => start(db,data,library,body),
        ("POST", ["sessions", session, "actions"]) => action(db,data,library,id(session)?,body),
        _ => Err(ApiError::missing("接口不存在")),
    }
}

fn save_group(db: &Connection, table: &str, body: &Value, id: Option<i64>) -> ApiResult {
    let name = text(body, "name").trim();
    if name.is_empty() || name.chars().count() > 200 {
        return Err(ApiError::bad("分组名称必须为 1 至 200 个字符"));
    }
    if db::one(
        db,
        &format!("SELECT id FROM {table} WHERE name=?1 AND (?2 IS NULL OR id!=?2)"),
        params![name, id],
    )?
    .is_some()
    {
        return Err(ApiError::new(409, "已有同名分组"));
    }
    let result = if let Some(id) = id {
        if db.execute(
            &format!("UPDATE {table} SET name=?1 WHERE id=?2"),
            params![name, id],
        )? == 0
        {
            return Err(ApiError::missing("分组不存在"));
        }
        id
    } else {
        db.execute(&format!("INSERT INTO {table}(name) VALUES (?1)"), [name])?;
        db.last_insert_rowid()
    };
    Ok(json!({"id":result,"name":name}))
}

pub fn save_entry(
    db: &Connection,
    library: Library,
    body: &Value,
    entry_id: Option<i64>,
) -> ApiResult<i64> {
    let group = number(body, "group_id");
    if db::one(
        db,
        &format!("SELECT id FROM {} WHERE id=?1", library.table("groups")),
        [group],
    )?
    .is_none()
    {
        return Err(ApiError::bad("请先选择有效分组"));
    }
    let english = text(body, "english")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let meaning = text(body, "translation").trim().replace("\\n", "\n");
    let kind = text(body, "item_type");
    if !english.bytes().any(|byte| byte.is_ascii_alphabetic()) || meaning.is_empty() {
        return Err(ApiError::bad("请填写英文和中文释义"));
    }
    if english.chars().count() > 300 || meaning.chars().count() > 5000 {
        return Err(ApiError::new(422, "词条或释义超过长度限制"));
    }
    if !matches!(kind, "word" | "phrase") {
        return Err(ApiError::bad("词条类型无效"));
    }
    let entries = library.table("entries");
    let normalized = db::normalize(&english);
    if db::one(db,&format!("SELECT id FROM {entries} WHERE group_id=?1 AND item_type=?2 AND normalized=?3 AND (?4 IS NULL OR id!=?4)"),
        params![group,kind,normalized,entry_id])?.is_some() {
        return Err(ApiError::new(409,"该分组已有相同类型的英文词条"));
    }
    let source = text(body, "source");
    if let Some(id) = entry_id {
        if db.execute(&format!("UPDATE {entries} SET group_id=?1,item_type=?2,english=?3,normalized=?4,translation=?5,source=?6 WHERE id=?7"),
            params![group,kind,english,normalized,meaning,source,id])? == 0 {
            return Err(ApiError::missing("词条不存在"));
        }
        return Ok(id);
    }
    db.execute(&format!("INSERT INTO {entries}(group_id,item_type,english,normalized,translation,source,in_mistake_book,mistake_consec,completed)
        VALUES (?1,?2,?3,?4,?5,?6,0,0,0)"),params![group,kind,english,normalized,meaning,source])?;
    Ok(db.last_insert_rowid())
}

fn entry_payload(db: &Connection, data: &Path, library: Library, mut row: Value) -> ApiResult {
    let name = db::one(
        db,
        &format!("SELECT name FROM {} WHERE id=?1", library.table("groups")),
        [number(&row, "group_id")],
    )?;
    row["group_name"] = name
        .map(|value| value["name"].clone())
        .unwrap_or_else(|| json!("已删除分组"));
    let word = row["item_type"] == "word";
    let english = text(&row, "english");
    let parts = if word {
        dictionary::parts(data, english, text(&row, "translation"), "")
    } else {
        String::new()
    };
    let ipa = if word {
        dictionary::ipa(data, english)
    } else {
        String::new()
    };
    let (definitions, link) = if word && !library.accumulated() {
        dictionary::definitions(data, english)
    } else {
        Default::default()
    };
    row["part_of_speech"] = json!(parts);
    row["phonetic_us"] = json!(ipa);
    row["english_definitions"] = json!(definitions);
    row["english_definition_source"] = json!(link);
    row["in_mistake_book"] = json!(yes(&row, "in_mistake_book"));
    if library.accumulated() {
        let recent = learning(db, number(&row, "id"))?;
        row["recent_accuracy"] = json!(recent.recent_accuracy());
        row["recent_attempts"] = json!(recent.recent);
        row["last_practiced_at"] = json!(
            recent
                .latest
                .as_deref()
                .map(|time| format!("{}Z", db::iso(time)))
        );
    }
    row.as_object_mut().unwrap().remove("normalized");
    Ok(row)
}

#[derive(Default)]
struct Learning {
    all: i64,
    correct: i64,
    recent: i64,
    recent_correct: i64,
    latest: Option<String>,
}

impl Learning {
    fn recent_accuracy(&self) -> Option<f64> {
        (self.recent > 0).then(|| self.recent_correct as f64 / self.recent as f64)
    }
    fn accuracy_ratio(&self) -> Option<(i128, i128)> {
        let all = i128::from(self.all);
        let recent = i128::from(self.recent);
        (recent > 0).then(|| {
            (
                4 * i128::from(self.recent_correct) * all + i128::from(self.correct) * recent,
                5 * recent * all,
            )
        })
    }
}

fn learning(db: &Connection, entry: i64) -> ApiResult<Learning> {
    let totals = db::one(
        db,
        "SELECT count(*) n,count(*) FILTER(WHERE choice_correct AND spelling_correct) correct,
        max(completed_at) latest FROM accumulation_review_logs WHERE entry_id=?1",
        [entry],
    )?
    .unwrap();
    let recent = db::one(db,"SELECT count(*) n,count(*) FILTER(WHERE choice_correct AND spelling_correct) correct FROM (
        SELECT choice_correct,spelling_correct FROM accumulation_review_logs WHERE entry_id=?1 ORDER BY completed_at DESC,id DESC LIMIT 10)",
        [entry])?.unwrap();
    Ok(Learning {
        all: number(&totals, "n"),
        correct: number(&totals, "correct"),
        recent: number(&recent, "n"),
        recent_correct: number(&recent, "correct"),
        latest: totals["latest"].as_str().map(str::to_owned),
    })
}

fn rank<T>(
    mut values: Vec<(i64, T)>,
    compare: impl Fn(&T, &T) -> Ordering,
) -> (HashMap<i64, i128>, i128) {
    values.sort_by(|a, b| compare(&a.1, &b.1));
    let mut result = HashMap::new();
    let n = values.len();
    let scale = 2 * n.saturating_sub(1).max(1) as i128;
    let mut start = 0;
    while start < n {
        let mut end = start + 1;
        while end < n && compare(&values[end].1, &values[start].1) == Ordering::Equal {
            end += 1;
        }
        let rank = if n == 1 {
            scale / 2
        } else {
            (start + end - 1) as i128
        };
        for (id, _) in &values[start..end] {
            result.insert(*id, rank);
        }
        start = end;
    }
    (result, scale)
}

fn prioritize(db: &Connection, entries: &mut Vec<Value>) -> ApiResult<()> {
    let mut accuracy = Vec::new();
    let mut elapsed = Vec::new();
    let mut counts = Vec::new();
    for entry in entries.iter() {
        let id = number(entry, "id");
        let stats = learning(db, id)?;
        if let Some(value) = stats.accuracy_ratio() {
            accuracy.push((id, value));
        }
        if let Some(value) = stats.latest {
            elapsed.push((id, std::cmp::Reverse(value)));
        }
        counts.push((id, -number(entry, "completed")));
    }
    let (accuracy, accuracy_scale) = rank(accuracy, |(left, lscale), (right, rscale)| {
        (right * lscale).cmp(&(left * rscale))
    });
    let (elapsed, elapsed_scale) = rank(elapsed, Ord::cmp);
    let (counts, count_scale) = rank(counts, Ord::cmp);
    // 通分后使用整数比较，分数相同的候选始终按旧版词条编号决定先后。
    let score = |entry: &Value| {
        let id = number(entry, "id");
        let neutral = if yes(entry, "in_mistake_book") {
            accuracy_scale
        } else {
            accuracy_scale / 2
        };
        3 * accuracy.get(&id).copied().unwrap_or(neutral) * elapsed_scale * count_scale
            + elapsed.get(&id).copied().unwrap_or(elapsed_scale / 2) * accuracy_scale * count_scale
            + counts.get(&id).copied().unwrap_or(count_scale / 2) * accuracy_scale * elapsed_scale
    };
    entries.sort_by(|a, b| {
        score(b)
            .cmp(&score(a))
            .then(number(a, "id").cmp(&number(b, "id")))
    });
    entries.truncate(50);
    Ok(())
}

fn choice_label(value: &str) -> String {
    static PARENS: OnceLock<Regex> = OnceLock::new();
    static ANNOTATION: OnceLock<Regex> = OnceLock::new();
    static ENGLISH: OnceLock<Regex> = OnceLock::new();
    static SPACE: OnceLock<Regex> = OnceLock::new();
    static SEPARATOR: OnceLock<Regex> = OnceLock::new();
    let value = value.replace("\\n", "\n");
    let annotation = ANNOTATION.get_or_init(|| {
        Regex::new(r"[A-Za-z]|正式|非正式|口语|旧式|用于|通常|尤指|此处|例如|如\s").unwrap()
    });
    let value = PARENS
        .get_or_init(|| Regex::new(r"[（(]([^）)]*)[）)]").unwrap())
        .replace_all(&value, |caps: &regex::Captures| {
            if annotation.is_match(&caps[1]) {
                String::new()
            } else {
                caps[0].to_owned()
            }
        });
    let value = ENGLISH
        .get_or_init(|| Regex::new(r"[A-Za-z][A-Za-z'’/-]*(?:\s*\.)?").unwrap())
        .replace_all(&value, "");
    let value = SPACE
        .get_or_init(|| Regex::new(r"[ \t]+").unwrap())
        .replace_all(&value, " ");
    SEPARATOR
        .get_or_init(|| Regex::new(r"\s*([；;，,、])\s*").unwrap())
        .replace_all(&value, "$1")
        .trim_matches(|c: char| c.is_whitespace() || "；;，,、:：/.-".contains(c))
        .to_owned()
}

fn options(entry: &Value, pool: &[Value], fallback: &[Value]) -> ApiResult<Vec<String>> {
    let correct = text(entry, "translation").trim();
    let label = choice_label(correct);
    let key = text(entry, "normalized");
    if label.is_empty() {
        return Err(ApiError::bad(format!(
            "“{}”缺少可显示的中文释义",
            text(entry, "english")
        )));
    }
    let excluded: HashSet<_> = pool
        .iter()
        .chain(fallback)
        .filter(|item| db::normalize(text(item, "english")) == key)
        .map(|item| db::normalize(text(item, "translation")))
        .collect();
    let mut seen = HashSet::from([db::normalize(&label)]);
    let mut selected = vec![correct.to_owned()];
    let mut rng = rand::rng();
    for values in [pool, fallback] {
        let mut values: Vec<_> = values.iter().collect();
        values.shuffle(&mut rng);
        for other in values {
            let translation = text(other, "translation").trim().replace("\\n", "\n");
            let label = db::normalize(&choice_label(&translation));
            if label.is_empty()
                || excluded.contains(&db::normalize(&translation))
                || db::normalize(text(other, "english")) == key
                || !seen.insert(label)
            {
                continue;
            }
            selected.push(translation);
            if selected.len() == 4 {
                break;
            }
        }
        if selected.len() == 4 {
            break;
        }
    }
    if selected.len() < 2 {
        return Err(ApiError::bad(format!(
            "“{}”缺少不同释义的干扰项，请先补充同类型词汇",
            text(entry, "english")
        )));
    }
    selected.shuffle(&mut rng);
    Ok(selected)
}

fn start(db: &mut Connection, data: &Path, library: Library, body: &Value) -> ApiResult {
    let group = body["group_id"].as_i64();
    let kind = body["item_type"].as_str().unwrap_or("all");
    let source = body["source"].as_str().unwrap_or("normal");
    let key = scope(group, kind, source)?;
    let sessions = library.table("sessions");
    let entries = library.table("entries");
    let items = library.table("session_items");
    let tx = db.transaction()?;
    let previous = db::one(
        &tx,
        &format!("SELECT id FROM {sessions} WHERE scope=?1"),
        [&key],
    )?;
    if let Some(row) = previous.as_ref().filter(|_| !yes(body, "restart")) {
        let result = session_payload(&tx, data, library, number(row, "id"))?;
        tx.commit()?;
        return Ok(result);
    }
    let mut selected = db::rows(
        &tx,
        &format!(
            "SELECT * FROM {entries} WHERE (?1 IS NULL OR group_id=?1)
        AND (?2='all' OR item_type=?2) AND (NOT ?3 OR in_mistake_book) ORDER BY id"
        ),
        params![group, kind, source == "mistake"],
    )?;
    if selected.is_empty() {
        return Err(ApiError::bad(if source == "mistake" {
            "当前范围没有错题"
        } else {
            "当前范围还没有词汇，请先添加或导入"
        }));
    }
    if library.accumulated() {
        prioritize(&tx, &mut selected)?;
    }
    selected.shuffle(&mut rand::rng());
    let mut pool = HashMap::new();
    for kind in selected
        .iter()
        .map(|row| text(row, "item_type"))
        .collect::<HashSet<_>>()
    {
        let local = db::rows(
            &tx,
            &format!("SELECT english,translation FROM {entries} WHERE item_type=?1"),
            [kind],
        )?;
        let sql = if kind == "word" {
            "SELECT headword english,translation FROM words"
        } else {
            "SELECT text english,translation FROM phrases"
        };
        let mut fallback = db::rows(&tx, sql, [])?;
        for row in &mut fallback {
            row["translation"] = json!(
                text(row, "translation")
                    .replace("\\n", "\n")
                    .split('\n')
                    .next()
                    .unwrap_or("")
            );
        }
        pool.insert(kind.to_owned(), (local, fallback));
    }
    if let Some(row) = previous {
        tx.execute(
            &format!("DELETE FROM {items} WHERE session_id=?1"),
            [number(&row, "id")],
        )?;
        tx.execute(
            &format!("DELETE FROM {sessions} WHERE id=?1"),
            [number(&row, "id")],
        )?;
    }
    tx.execute(&format!("INSERT INTO {sessions}(scope,source,cursor,version,updated_at,receipts) VALUES (?1,?2,0,0,?3,'[]')"),
        params![key,source,db::now()])?;
    let session = tx.last_insert_rowid();
    for (position, entry) in selected.into_iter().enumerate() {
        let (local, fallback) = &pool[text(&entry, "item_type")];
        let choices = options(&entry, local, fallback)?;
        let entry_id = number(&entry, "id");
        let snapshot = entry_payload(&tx, data, library, entry)?;
        tx.execute(&format!("INSERT INTO {items}(session_id,entry_id,position,snapshot,options,stage,spell_wrong,rating)
            VALUES (?1,?2,?3,?4,?5,'choice',0,'')"),params![session,entry_id,position as i64,snapshot.to_string(),json!(choices).to_string()])?;
    }
    let result = session_payload(&tx, data, library, session)?;
    tx.commit()?;
    Ok(result)
}

fn session_payload(db: &Connection, data: &Path, library: Library, session: i64) -> ApiResult {
    let sessions = library.table("sessions");
    let entries = library.table("entries");
    let items = library.table("session_items");
    let round = db::one(
        db,
        &format!("SELECT * FROM {sessions} WHERE id=?1"),
        [session],
    )?
    .ok_or_else(|| ApiError::missing("这一轮已被重新开始，请返回复习页"))?;
    db.execute(&format!("UPDATE {items} SET stage='skipped' WHERE session_id=?1 AND stage NOT IN ('skipped','done')
        AND NOT EXISTS (SELECT 1 FROM {entries} WHERE {entries}.id={items}.entry_id)"),[session])?;
    let questions = db::rows(
        db,
        &format!(
            "SELECT q.*,e.in_mistake_book,e.mistake_consec FROM {items} q
        LEFT JOIN {entries} e ON e.id=q.entry_id WHERE q.session_id=?1 ORDER BY position"
        ),
        [session],
    )?;
    let mut cursor = number(&round, "cursor") as usize;
    while questions
        .get(cursor)
        .is_some_and(|q| q["stage"] == "skipped")
    {
        cursor += 1;
    }
    if cursor as i64 != number(&round, "cursor") {
        db.execute(
            &format!("UPDATE {sessions} SET cursor=?1 WHERE id=?2"),
            params![cursor as i64, session],
        )?;
    }
    let current = questions.get(cursor);
    let mut payload = json!({"id":session,"version":round["version"],"source":round["source"],"finished":current.is_none(),
        "total":questions.iter().filter(|q|q["stage"]!="skipped").count(),
        "completed":questions.iter().filter(|q|q["stage"]=="done").count(),
        "correct":questions.iter().filter(|q|q["stage"]=="done" && q["rating"]=="good").count(),
        "updated_at":db::iso(text(&round,"updated_at")),"current":null});
    if let Some(question) = current {
        let mut snapshot: Value = serde_json::from_str(text(question, "snapshot"))?;
        if snapshot["item_type"] == "word" {
            let english = text(&snapshot, "english").to_owned();
            if text(&snapshot, "part_of_speech").is_empty() {
                snapshot["part_of_speech"] = json!(dictionary::parts(
                    data,
                    &english,
                    text(&snapshot, "translation"),
                    ""
                ));
            }
            if text(&snapshot, "phonetic_us").is_empty() {
                snapshot["phonetic_us"] = json!(dictionary::ipa(data, &english));
            }
            if !library.accumulated() {
                let (definitions, link) = dictionary::definitions(data, &english);
                snapshot["english_definitions"] = json!(definitions);
                snapshot["english_definition_source"] = json!(link);
            }
        }
        let correct = text(&snapshot, "translation").to_owned();
        let translation_label = choice_label(&correct);
        let saved: Vec<String> = serde_json::from_str(text(question, "options"))?;
        let mut seen = HashSet::from([db::normalize(&translation_label)]);
        let options: Vec<_> = saved
            .iter()
            .filter(|option| {
                let key = db::normalize(&choice_label(option));
                option.as_str() == correct || (!key.is_empty() && seen.insert(key))
            })
            .collect();
        snapshot["option_labels"] = json!(
            options
                .iter()
                .map(|option| choice_label(option))
                .collect::<Vec<_>>()
        );
        snapshot["options"] = json!(options);
        snapshot["translation_label"] = json!(if translation_label.is_empty() {
            correct
        } else {
            translation_label
        });
        snapshot["question_id"] = question["id"].clone();
        for field in ["stage", "picked", "rating"] {
            snapshot[field] = question[field].clone();
        }
        for field in ["spell_wrong", "in_mistake_book"] {
            snapshot[field] = json!(yes(question, field));
        }
        snapshot["mistake_consec"] = json!(number(question, "mistake_consec"));
        payload["current"] = snapshot;
        let upcoming: Vec<Value> = questions
            .iter()
            .skip(cursor + 1)
            .filter(|q| q["stage"] == "choice")
            .take(2)
            .map(|q| serde_json::from_str::<Value>(text(q, "snapshot")))
            .collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .map(|entry| json!({"english":entry["english"],"translation":entry["translation"]}))
            .collect();
        payload["upcoming_speech"] = json!(upcoming);
    }
    Ok(payload)
}

fn action(
    db: &mut Connection,
    data: &Path,
    library: Library,
    session: i64,
    body: &Value,
) -> ApiResult {
    let sessions = library.table("sessions");
    let entries = library.table("entries");
    let items = library.table("session_items");
    let receipt = text(body, "request_id");
    if receipt.is_empty() || receipt.chars().count() > 100 {
        return Err(ApiError::new(422, "请求编号无效"));
    }
    let tx = db.transaction()?;
    let row = db::one(
        &tx,
        &format!("SELECT * FROM {sessions} WHERE id=?1"),
        [session],
    )?
    .ok_or_else(|| ApiError::missing("这一轮已被重新开始，请返回复习页"))?;
    let mut receipts: Vec<String> = serde_json::from_str(text(&row, "receipts"))?;
    if !receipts.iter().any(|value| value == receipt) {
        if row["version"] != body["version"] {
            return Err(ApiError::new(409, "进度已更新，请继续当前题目"));
        }
        let cursor = number(&row, "cursor");
        let question = db::one(
            &tx,
            &format!("SELECT * FROM {items} WHERE session_id=?1 AND position=?2"),
            params![session, cursor],
        )?
        .filter(|q| q["id"] == body["question_id"])
        .ok_or_else(|| ApiError::new(409, "当前题目已变化，请刷新进度"))?;
        let entry = number(&question, "entry_id");
        let qid = number(&question, "id");
        if question["stage"] == "done"
            || db::count(
                &tx,
                &format!("SELECT EXISTS(SELECT 1 FROM {entries} WHERE id=?1)"),
                [entry],
            )? != 0
        {
            let value = text(body, "value");
            let snapshot: Value = serde_json::from_str(text(&question, "snapshot"))?;
            let correct = text(&snapshot, "translation");
            let mut next = cursor;
            let mark_wrong = || {
                tx.execute(
                    &format!("UPDATE {entries} SET in_mistake_book=1,mistake_consec=0 WHERE id=?1"),
                    [entry],
                )
            };
            match (text(body, "action"), text(&question, "stage")) {
                ("choice", "choice") => {
                    let options: Vec<String> = serde_json::from_str(text(&question, "options"))?;
                    if !options.iter().any(|option| option == value) {
                        return Err(ApiError::bad("请选择题目中的选项"));
                    }
                    tx.execute(
                        &format!("UPDATE {items} SET picked=?1,stage='spell' WHERE id=?2"),
                        params![value, qid],
                    )?;
                    if value != correct {
                        mark_wrong()?;
                    }
                }
                ("spell", "spell") => {
                    if value.trim().is_empty() {
                        return Err(ApiError::bad("请输入英文拼写"));
                    }
                    if db::normalize(value) != db::normalize(text(&snapshot, "english")) {
                        tx.execute(
                            &format!("UPDATE {items} SET spell_wrong=1 WHERE id=?1"),
                            [qid],
                        )?;
                        mark_wrong()?;
                    } else {
                        let choice = question["picked"].as_str() == Some(correct);
                        let spell = !yes(&question, "spell_wrong");
                        let rating = if !choice {
                            "again"
                        } else if !spell {
                            "hard"
                        } else {
                            "good"
                        };
                        tx.execute(
                            &format!("UPDATE {items} SET stage='done',rating=?1 WHERE id=?2"),
                            params![rating, qid],
                        )?;
                        if rating == "good" {
                            tx.execute(&format!("UPDATE {entries} SET in_mistake_book=(in_mistake_book AND mistake_consec<2),
                                mistake_consec=CASE WHEN in_mistake_book AND mistake_consec<2 THEN mistake_consec+1 ELSE 0 END WHERE id=?1"),[entry])?;
                        } else {
                            mark_wrong()?;
                        }
                        tx.execute(
                            &format!("UPDATE {entries} SET completed=completed+1 WHERE id=?1"),
                            [entry],
                        )?;
                        if library.accumulated() {
                            tx.execute("INSERT INTO accumulation_review_logs(entry_id,session_id,question_id,choice_correct,spelling_correct,completed_at)
                                VALUES (?1,?2,?3,?4,?5,?6)",params![entry,session,qid,choice,spell,db::utc_now()])?;
                        }
                    }
                }
                ("next", "done") => next += 1,
                _ => return Err(ApiError::new(409, "当前答题阶段已变化，请刷新进度")),
            }
            receipts.push(receipt.to_owned());
            tx.execute(&format!("UPDATE {sessions} SET cursor=?1,version=version+1,updated_at=?2,receipts=?3 WHERE id=?4"),
                params![next,db::now(),json!(receipts).to_string(),session])?;
        }
    }
    let result = session_payload(&tx, data, library, session)?;
    tx.commit()?;
    Ok(result)
}

fn parse_text(raw: &str) -> Vec<Value> {
    static NUMBER: OnceLock<Regex> = OnceLock::new();
    static SPLIT: OnceLock<Regex> = OnceLock::new();
    static TRAILING: OnceLock<Regex> = OnceLock::new();
    let number = NUMBER.get_or_init(|| Regex::new(r"^\d+[.、)）]\s*").unwrap());
    let split = SPLIT.get_or_init(|| Regex::new(r"\t+|\s*\|\s*").unwrap());
    let trailing = TRAILING.get_or_init(|| {
        Regex::new(r"(?:\s*/[^/]+/.*|\s+(?:n|v|vt|vi|adj|adv|a|ad|prep|conj)\.|\s*[:：=—–]+)\s*$")
            .unwrap()
    });
    let mut rows: Vec<Value> = Vec::new();
    for line in raw
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.chars().all(|c| c.is_numeric()))
    {
        let content = number.replace(line, "");
        let (english, translation) = if let Some(separator) = split.find(&content) {
            (&content[..separator.start()], &content[separator.end()..])
        } else if let Some((index, _)) = content
            .char_indices()
            .find(|(_, c)| ('\u{3400}'..='\u{9fff}').contains(c))
        {
            content.split_at(index)
        } else if content.bytes().any(|byte| byte.is_ascii_alphabetic()) {
            (content.as_ref(), "")
        } else if let Some(last) = rows.last_mut().filter(|last| {
            !text(last, "english").is_empty() && text(last, "translation").is_empty()
        }) {
            last["translation"] = json!(line);
            continue;
        } else {
            ("", content.as_ref())
        };
        let english = trailing.replace(english, "");
        let english = english.trim();
        let translation = translation.trim();
        if matches!(
            english.to_lowercase().as_str(),
            "英文" | "english" | "word" | "单词"
        ) && matches!(translation, "中文" | "释义" | "中文释义" | "meaning")
        {
            continue;
        }
        rows.push(json!({"english":english,"translation":translation,"item_type":if english.contains(' ') {"phrase"}else{"word"},
            "source":"批量粘贴","raw":line}));
    }
    rows
}
