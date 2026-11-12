mod ai;
mod api;
mod classroom;
mod codex;
mod db;
mod dictionary;
mod grading;
mod media;
mod practice;
mod process;
mod profiles;
mod questions;
mod settings;
mod short;
mod study;

use anyhow::{Context, Result};
use axum::{Router, extract::DefaultBodyLimit, http::StatusCode, routing::any};
use std::{env, path::PathBuf, sync::Arc};
use tokio::net::TcpListener;
use tower_http::services::{ServeDir, ServeFile};

fn backend_directory() -> Result<PathBuf> {
    let from_executable = env::current_exe()?
        .ancestors()
        .find(|dir| dir.join("data/questions.json").is_file())
        .map(PathBuf::from);
    from_executable
        .or_else(|| {
            let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
            path.join("data/questions.json").is_file().then_some(path)
        })
        .context("未找到后端题库目录")
}

#[tokio::main]
async fn main() -> Result<()> {
    let backend = backend_directory()?;
    let data = env::var_os("ENGLISH_PLATFORM_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| backend.join("data"));
    let dist = backend.join("../frontend/dist");
    let seed_data = backend.join("data");
    let port = env::var("ENGLISH_PLATFORM_PORT")
        .unwrap_or_else(|_| "8930".into())
        .parse::<u16>()?;
    let listener = TcpListener::bind(("127.0.0.1", port))
        .await
        .with_context(|| format!("无法在本机端口 {port} 启动英语学习平台"))?;
    let connection = db::open(&data, &seed_data)?;
    let app = Arc::new(api::App {
        db: connection.into(),
        data: seed_data.clone(),
        backend,
        storage: data,
        speech: Default::default(),
    });
    let router = Router::new()
        .route(
            "/api/{*path}",
            any(api::handle).layer(DefaultBodyLimit::max(30 * 1024 * 1024 + 1)),
        )
        .nest_service(
            "/data-static/charts",
            ServeDir::new(seed_data.join("charts")),
        )
        .route(
            "/data-static/{*path}",
            any(|| async { StatusCode::NOT_FOUND }),
        )
        .nest_service("/assets", ServeDir::new(dist.join("assets")))
        .fallback_service(ServeDir::new(&dist).fallback(ServeFile::new(dist.join("index.html"))))
        .with_state(app);
    let url = format!("http://127.0.0.1:{}/", listener.local_addr()?.port());
    println!("英语学习平台已就绪 {url}");
    if env::args_os().any(|arg| arg == "--open-browser") {
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            if let Err(error) = std::process::Command::new("rundll32.exe")
                .args(["url.dll,FileProtocolHandler", &url])
                .creation_flags(0x0800_0000)
                .spawn()
            {
                eprintln!("请在浏览器打开 {url}，自动打开失败：{error}");
            }
        }
    }
    axum::serve(listener, router)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
