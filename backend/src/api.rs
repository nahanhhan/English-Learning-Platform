use axum::{
    Json,
    body::{Body, Bytes},
    extract::{Path, RawQuery, State, rejection::BytesRejection},
    http::{Method, StatusCode, header},
    response::{Html, IntoResponse, Response},
};
use rusqlite::Connection;
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{Arc, Mutex},
};

pub struct App {
    pub db: Mutex<Connection>,
    pub data: PathBuf,
    pub backend: PathBuf,
    pub storage: PathBuf,
    pub speech: crate::media::SpeechGate,
}

pub struct ApiError {
    status: StatusCode,
    message: String,
}

pub type ApiResult<T = Value> = Result<T, ApiError>;

impl ApiError {
    pub fn new(status: u16, message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::from_u16(status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
            message: message.into(),
        }
    }

    pub fn bad(message: impl Into<String>) -> Self {
        Self::new(400, message)
    }

    pub fn missing(message: impl Into<String>) -> Self {
        Self::new(404, message)
    }

    pub fn is_conflict(&self) -> bool {
        self.status == StatusCode::CONFLICT
    }

    pub fn message(&self) -> &str {
        &self.message
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({"detail": self.message}))).into_response()
    }
}

impl From<rusqlite::Error> for ApiError {
    fn from(error: rusqlite::Error) -> Self {
        eprintln!("数据库请求失败：{error}");
        Self::new(500, "本机数据库暂时不可用")
    }
}

impl From<serde_json::Error> for ApiError {
    fn from(_: serde_json::Error) -> Self {
        Self::bad("JSON 数据格式无效")
    }
}

pub fn text<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or_default()
}

pub fn number(value: &Value, key: &str) -> i64 {
    value.get(key).and_then(Value::as_i64).unwrap_or_default()
}

pub fn yes(value: &Value, key: &str) -> bool {
    value
        .get(key)
        .and_then(Value::as_bool)
        .unwrap_or_else(|| number(value, key) != 0)
}

pub struct Query(HashMap<String, String>);

impl Query {
    pub fn get(&self, name: &str) -> Option<&str> {
        self.0.get(name).map(String::as_str)
    }

    pub fn integer(&self, name: &str) -> ApiResult<Option<i64>> {
        self.get(name)
            .map(|value| {
                value
                    .parse()
                    .map_err(|_| ApiError::new(422, format!("{name} 必须为整数")))
            })
            .transpose()
    }

    pub fn flag(&self, name: &str) -> bool {
        matches!(self.get(name), Some("1" | "true" | "True"))
    }
}

pub fn db_result(app: &App, work: impl FnOnce(&mut Connection) -> ApiResult) -> ApiResult {
    let mut db = app
        .db
        .lock()
        .map_err(|_| ApiError::new(500, "本机数据库暂时不可用"))?;
    work(&mut db)
}

pub async fn handle(
    State(app): State<Arc<App>>,
    Path(path): Path<String>,
    RawQuery(raw): RawQuery,
    method: Method,
    body: Result<Bytes, BytesRejection>,
) -> Response<Body> {
    let query = Query(
        url::form_urlencoded::parse(raw.as_deref().unwrap_or("").as_bytes())
            .into_owned()
            .collect(),
    );
    let work = tokio::task::spawn_blocking(move || -> ApiResult<Response> {
        let parts: Vec<_> = path.trim_end_matches('/').split('/').collect();
        if method == Method::GET {
            match parts.as_slice() {
                ["docs"] => return Ok(Html(include_str!("api-docs.html")).into_response()),
                ["openapi.json"] => {
                    return Ok((
                        [(header::CONTENT_TYPE, "application/json")],
                        include_str!("openapi.json"),
                    )
                        .into_response());
                }
                _ => {}
            }
        }
        let body = body.map_err(|_| ApiError::new(413, "请求内容超过处理限制"))?;
        if method == Method::POST
            && matches!(
                parts.as_slice(),
                ["classroom" | "accumulation", "imports", "file"]
            )
        {
            return Ok(Json(crate::media::document(
                &app,
                query.get("filename").unwrap_or_default(),
                body.to_vec(),
            )?)
            .into_response());
        }
        let body = if body.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&body)?
        };
        if method == Method::POST && parts.as_slice() == ["speech"] {
            return crate::media::speech(&app, &body);
        }
        let result = match (method.as_str(), parts.as_slice()) {
            ("GET", ["stats", "dashboard"]) => db_result(&app, crate::questions::dashboard),
            ("GET", ["questions"]) => {
                db_result(&app, |db| crate::questions::list(db, &query, &app.data))
            }
            ("GET", ["questions", "meta"]) => db_result(&app, crate::questions::meta),
            ("GET", ["questions", id]) => {
                db_result(&app, |db| crate::questions::detail(db, id, &app.data))
            }
            (method, ["vocab" | "phrases", ..]) => db_result(&app, |db| {
                crate::study::route(db, &app.data, method, &parts, &query, &body)
            }),
            (method, ["classroom" | "accumulation", ..]) => db_result(&app, |db| {
                crate::classroom::route(db, &app.data, method, &parts, &query, &body)
            }),
            (method, ["settings", rest @ ..]) => crate::settings::route(&app, method, rest, &body),
            (method, ["practice", rest @ ..]) => {
                crate::practice::route(&app, method, rest, &query, &body)
            }
            (method, ["short-translation", rest @ ..]) => {
                crate::short::route(&app, method, rest, &query, &body)
            }
            _ => {
                drop(body);
                Err(ApiError::missing("接口不存在"))
            }
        }?;
        Ok(Json(result).into_response())
    })
    .await;
    match work {
        Ok(Ok(response)) => response,
        Ok(Err(error)) => error.into_response(),
        Err(error) => {
            eprintln!("接口处理异常：{error}");
            ApiError::new(500, "接口处理失败").into_response()
        }
    }
}
