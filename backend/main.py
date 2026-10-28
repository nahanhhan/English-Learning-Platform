import os
import sys

# 保证 scripts 目录的数据文件可定位
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine, DATA_DIR
from app.routers import classroom, phrases, practice, questions, settings, speech, stats, vocab
from app.services.classroom import ClassroomError

app = FastAPI(title="英语学习平台", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(ClassroomError)
async def classroom_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# 图表等数据文件
from fastapi.staticfiles import StaticFiles as _StaticFiles  # noqa: E402

app.mount("/data-static", _StaticFiles(directory=DATA_DIR), name="data")

for r in (speech.router, classroom.router, classroom.accumulation_router, questions.router, practice.router, vocab.router, phrases.router,
          stats.router, settings.router):
    app.include_router(r)

# 托管前端构建产物
FRONTEND_DIST = os.path.join(os.path.dirname(DATA_DIR), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))  # 不会到达
        f = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    # 首次启动导入题库与词库
    from scripts.seed import ensure_seeded
    ensure_seeded()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8930, log_level="info")
