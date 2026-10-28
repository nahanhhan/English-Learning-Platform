"""平时积累的初始内容、板块隔离和共用答题流程。"""
import json
import re
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import Base, get_db
from app.models import (AccumulationEntry, AccumulationGroup, ClassroomEntry, ClassroomGroup,
                        ClassroomSession, UserSetting)
from app.routers.classroom import accumulation_router, router
from app.services import classroom as service
from app.services.parts_of_speech import parts_of_speech
from scripts.seed_accumulation import INITIAL_PATH, seed_accumulation


@pytest.fixture
def client_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accumulation.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router)
    app.include_router(accumulation_router)

    def connection():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = connection

    @app.exception_handler(service.ClassroomError)
    async def error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    with factory() as db:
        seed_accumulation(db)
    with TestClient(app) as client, factory() as db:
        yield client, db, factory
    engine.dispose()


def action(client, session, kind, value="", request_id=None):
    response = client.post(f"/api/accumulation/sessions/{session['id']}/actions", json={
        "question_id": session["current"]["question_id"], "version": session["version"],
        "request_id": request_id or uuid.uuid4().hex, "action": kind, "value": value,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_notes_cover_all_paragraphs_and_normalized_entries(client_db):
    client, db, _ = client_db
    data = json.loads(INITIAL_PATH.read_text(encoding="utf-8"))
    entries = client.get("/api/accumulation/entries?page_size=100").json()["items"]
    assert len(entries) == 23
    assert sum(e["item_type"] == "word" for e in entries) == 19
    assert sum(e["item_type"] == "phrase" for e in entries) == 4
    assert len({e["english"] for e in entries}) == 23
    assert {int(re.search(r"第(\d+)段", e["source"])[1]) for e in entries} == set(range(1, 21))
    assert data["source_paragraphs"] == 20 and len(data["source_sha256"]) == 64
    by_name = {e["english"]: e for e in entries}
    assert {"utterly", "completely", "conjure up", "be deprived of", "a dirty word", "a body of"} <= by_name.keys()
    assert by_name["repute"]["part_of_speech"] == "n."
    assert by_name["reputed"]["part_of_speech"] == "adj."
    assert "整理说明" in by_name["reputed"]["source"]
    assert all(parts_of_speech(e["english"], e["translation"]) for e in entries if e["item_type"] == "word")
    assert db.query(ClassroomEntry).count() == db.query(ClassroomGroup).count() == 0


def test_seed_once_preserves_user_edits_and_deletions(client_db):
    _, db, _ = client_db
    word = db.query(AccumulationEntry).filter_by(english="utterly").one()
    word.translation = "adv. 用户补充释义"
    word.in_mistake_book = True
    word.mistake_consec = 2
    removed = db.query(AccumulationEntry).filter_by(english="completely").one()
    db.delete(removed)
    db.commit()
    seed_accumulation(db)
    assert db.query(AccumulationEntry).count() == 22
    assert word.translation == "adv. 用户补充释义" and word.mistake_consec == 2
    assert not db.query(AccumulationEntry).filter_by(english="completely").count()
    assert db.get(UserSetting, "accumulation_notes_20261028_v1") is not None


@pytest.mark.parametrize("kind", ["word", "phrase"])
def test_choice_spelling_resume_retries_and_three_correct_exit(client_db, kind):
    client, db, factory = client_db
    session = client.post("/api/accumulation/sessions", json={"item_type": kind}).json()
    first = session["current"]
    assert first["item_type"] == kind
    assert len(first["options"]) == len(set(first["options"])) == 4
    wrong = next(option for option in first["options"] if option != first["translation"])
    session = action(client, session, "choice", wrong)
    assert session["current"]["stage"] == "spell" and session["current"]["in_mistake_book"]
    session = action(client, session, "spell", "misspelled")
    resumed = client.get(f"/api/accumulation/sessions/current?item_type={kind}").json()
    assert resumed["current"] == session["current"] and resumed["current"]["spell_wrong"]
    previous = session
    session = action(client, session, "spell", first["english"], "finish-once")
    assert session["current"]["rating"] == "again"
    retried = action(client, previous, "spell", first["english"], "finish-once")
    assert retried["completed"] == session["completed"] == 1
    assert client.get("/api/classroom/sessions/current").json() is None
    for streak in (1, 2, 3):
        session = client.post("/api/accumulation/sessions", json={
            "item_type": kind, "source": "mistake", "restart": True}).json()
        assert session["total"] == 1 and session["current"]["id"] == first["id"]
        session = action(client, session, "choice", session["current"]["translation"])
        session = action(client, session, "spell", first["english"])
        assert session["current"]["in_mistake_book"] == (streak < 3)
        assert session["current"]["mistake_consec"] == (streak if streak < 3 else 0)
    with factory() as reopened:
        assert reopened.get(AccumulationEntry, first["id"]).completed == 4
    assert client.get("/api/accumulation/entries?mistakes=true").json()["total"] == 0
    assert db.query(ClassroomSession).count() == 0


def test_same_names_crud_import_and_delete_are_isolated(client_db):
    client, db, _ = client_db
    names = {}
    for library in ("classroom", "accumulation"):
        response = client.post(f"/api/{library}/groups", json={"name": "同名分组"})
        assert response.status_code == 200
        names[library] = response.json()["id"]
        created = client.post(f"/api/{library}/entries", json={
            "group_id": names[library], "item_type": "word", "english": "sharedword",
            "translation": "n. " + library,
        })
        assert created.status_code == 200
    classroom_entry = client.get("/api/classroom/entries?search=sharedword").json()["items"][0]
    accumulation_entry = client.get("/api/accumulation/entries?search=sharedword").json()["items"][0]
    assert classroom_entry["translation"] != accumulation_entry["translation"]
    changed = client.put(f"/api/accumulation/entries/{accumulation_entry['id']}", json={
        "group_id": names["accumulation"], "item_type": "word", "english": "sharedword",
        "translation": "n. 仅修改积累",
    })
    assert changed.status_code == 200
    assert client.get("/api/classroom/entries?search=sharedword").json()["items"][0] == classroom_entry
    preview = client.post("/api/accumulation/imports/text", json={"text": "newword | 新词"}).json()
    rows = [{**row, "group_id": names["accumulation"]} for row in preview["rows"]]
    for expected in ({"added": 1, "skipped": 0}, {"added": 0, "skipped": 1}):
        assert client.post("/api/accumulation/imports/confirm", json={"rows": rows}).json() == expected
    assert client.get("/api/classroom/entries?search=newword").json()["total"] == 0
    assert client.delete(f"/api/accumulation/groups/{names['accumulation']}").status_code == 200
    assert client.get("/api/accumulation/entries?search=sharedword").json()["total"] == 0
    assert client.get("/api/classroom/entries?search=sharedword").json()["items"][0] == classroom_entry


def test_old_classroom_session_survives_adding_new_library(client_db):
    client, db, _ = client_db
    group = client.post("/api/classroom/groups", json={"name": "既有课内"}).json()["id"]
    for i in range(4):
        assert client.post("/api/classroom/entries", json={"group_id": group, "item_type": "word",
            "english": f"existingword{i}", "translation": f"n. 既有释义{i}"}).status_code == 200
    session = client.post("/api/classroom/sessions", json={"group_id": group}).json()
    old_rows = [(e.id, e.english, e.translation) for e in db.query(ClassroomEntry).order_by(ClassroomEntry.id)]
    seed_accumulation(db)
    accumulated = client.post("/api/accumulation/sessions", json={}).json()
    assert accumulated["total"] == 23
    assert client.get(f"/api/classroom/sessions/current?group_id={group}").json() == session
    assert [(e.id, e.english, e.translation) for e in db.query(ClassroomEntry).order_by(ClassroomEntry.id)] == old_rows
