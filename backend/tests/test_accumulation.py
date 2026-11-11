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
                        ClassroomSession, AccumulationSessionItem, UserSetting)
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
    assert len(entries) == 95
    assert sum(e["item_type"] == "word" for e in entries) == 78
    assert sum(e["item_type"] == "phrase" for e in entries) == 17
    assert len({e["english"] for e in entries}) == 95
    assert {int(re.search(r"第(\d+)段", e["source"])[1]) for e in entries} == set(range(1, 92))
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
    assert db.query(AccumulationEntry).count() == 94
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
    assert accumulated["total"] == 50
    assert client.get(f"/api/classroom/sessions/current?group_id={group}").json() == session
    assert [(e.id, e.english, e.translation) for e in db.query(ClassroomEntry).order_by(ClassroomEntry.id)] == old_rows


@pytest.mark.parametrize("count", [1, 49, 50, 51, 75])
def test_accumulation_round_size_boundaries_and_classroom_unchanged(client_db, count):
    client, db, _ = client_db
    for library in ("accumulation", "classroom"):
        Entry, Group, _, Question = service.library_models(library)
        group = Group(name=f"边界{count}")
        db.add(group)
        db.flush()
        for i in range(count):
            service.save_entry(db, {"group_id": group.id, "item_type": "word",
                "english": f"boundary{i}", "translation": f"n. 边界释义{i}"},
                commit=False, library=library)
        # 单条范围也能从同库其他分组获取干扰项，不能补成额外题目。
        other = Group(name=f"干扰来源{count}")
        db.add(other)
        db.flush()
        service.save_entry(db, {"group_id": other.id, "item_type": "word",
            "english": "distractor", "translation": "n. 不参与本轮"},
            commit=False, library=library)
        db.commit()
        response = client.post(f"/api/{library}/sessions", json={"group_id": group.id})
        assert response.status_code == 200, response.text
        session = response.json()
        expected = min(count, 50) if library == "accumulation" else count
        assert session["total"] == expected
        rows = db.query(Question).filter_by(session_id=session["id"]).all()
        assert len(rows) == len({q.entry_id for q in rows}) == expected
        assert all(db.get(Entry, q.entry_id).group_id == group.id for q in rows)


@pytest.mark.parametrize("kind", ["all", "word", "phrase"])
@pytest.mark.parametrize("source", ["normal", "mistake"])
def test_accumulation_selects_scoped_candidates_then_shuffles_display(client_db, monkeypatch, kind, source):
    client, db, _ = client_db
    group = AccumulationGroup(name="抽样范围")
    db.add(group)
    db.flush()
    for item_type in ("word", "phrase"):
        for i in range(70):
            entry = service.save_entry(db, {"group_id": group.id, "item_type": item_type,
                "english": f"sample {item_type} {i}", "translation": f"{item_type}释义{i}"},
                commit=False, library="accumulation")
            entry.in_mistake_book = i < 60
    db.commit()
    expected = [e.id for e in service.filtered(db, group.id, kind,
        mistakes=source == "mistake", library="accumulation")]
    round_number = 0

    def controlled_shuffle(values):
        nonlocal round_number
        if values and isinstance(values[0], AccumulationEntry):
            round_number += 1
            # 选定相同优先级的前 50 条后，两轮展示顺序仍可不同。
            if round_number == 1:
                values.reverse()
        elif values and isinstance(values[0], str):
            shift = round_number % len(values)
            values[:] = values[shift:] + values[:shift]

    monkeypatch.setattr(service.random, "shuffle", controlled_shuffle)
    body = {"group_id": group.id, "item_type": kind, "source": source}
    orders, answer_positions = [], []
    for restart in (False, True):
        response = client.post("/api/accumulation/sessions", json={**body, "restart": restart})
        assert response.status_code == 200, response.text
        session = response.json()
        assert session["total"] == 50
        rows = db.query(AccumulationSessionItem).filter_by(session_id=session["id"]).order_by(
            AccumulationSessionItem.position).all()
        orders.append([q.entry_id for q in rows])
        assert len(set(orders[-1])) == 50
        positions = {}
        for q in rows:
            options = json.loads(q.options)
            correct = json.loads(q.snapshot)["translation"]
            assert len(options) == len(set(options)) == 4
            assert options.count(correct) == 1
            positions[q.entry_id] = options.index(correct)
        answer_positions.append(positions)
    assert orders == [list(reversed(expected[:50])), expected[:50]]
    assert set(answer_positions[0].values()) == {3}
    assert set(answer_positions[1].values()) == {2}
    overlap = set(orders[0]) & set(orders[1])
    assert all(answer_positions[0][i] != answer_positions[1][i] for i in overlap)
    assert [e.id for e in service.filtered(db, group.id, kind,
        mistakes=source == "mistake", library="accumulation")] == expected


@pytest.mark.parametrize("legacy", [False, True])
def test_accumulation_resume_preserves_sample_and_legacy_large_round(client_db, monkeypatch, legacy):
    client, db, factory = client_db
    session = client.post("/api/accumulation/sessions", json={}).json()
    if legacy:
        # 模拟上线前已经保存的 86 题快照；升级不截断旧轮次。
        selected = {q.entry_id for q in db.query(AccumulationSessionItem).filter_by(session_id=session["id"])}
        legacy_entries = db.query(AccumulationEntry).filter(
            AccumulationEntry.id.notin_(selected)
        ).order_by(AccumulationEntry.id).limit(36).all()
        for position, entry in enumerate(legacy_entries, start=50):
            db.add(AccumulationSessionItem(session_id=session["id"], entry_id=entry.id,
                position=position, snapshot=json.dumps(service.entry_payload(db, entry, library="accumulation")),
                options=json.dumps([entry.translation, "干扰释义"])))
        db.commit()
    first = session["current"]
    wrong = next(o for o in first["options"] if o != first["translation"])
    session = action(client, session, "choice", wrong)
    session = action(client, session, "spell", "incorrect")
    assert session["total"] == (86 if legacy else 50)

    def snapshot(connection):
        return [(q.id, q.entry_id, q.position, q.snapshot, q.options, q.stage, q.picked, q.spell_wrong)
            for q in connection.query(AccumulationSessionItem).filter_by(session_id=session["id"]).order_by(
                AccumulationSessionItem.position)]

    before = snapshot(db)
    with monkeypatch.context() as patch:
        def must_not_shuffle(values):
            raise AssertionError("续练不能重新抽题或打乱选项")
        patch.setattr(service.random, "shuffle", must_not_shuffle)
        with factory() as reopened:
            assert service.start(reopened, library="accumulation") == session
            assert snapshot(reopened) == before
        assert client.get("/api/accumulation/sessions/current").json() == session
        assert client.post("/api/accumulation/sessions", json={}).json() == session
    restarted = client.post("/api/accumulation/sessions", json={"restart": True}).json()
    assert restarted["total"] == 50 and restarted["id"] != session["id"]
    db.expire_all()
    entry = db.get(AccumulationEntry, first["id"])
    assert entry.in_mistake_book and entry.mistake_consec == 0 and entry.completed == 0


def test_incremental_notes_preserve_existing_data_and_skip_other_group_duplicates(client_db):
    from scripts.seed_accumulation import UPDATE_PATH
    _, db, _ = client_db
    data = json.loads(UPDATE_PATH.read_text(encoding="utf-8"))
    assert len(data["groups"][0]["entries"]) == 27
    assert data["source_paragraph_range"] == [21, 47]
    # 模拟升级前已有旧批次，以及用户在其他组录入的同一单词。
    old = db.query(AccumulationEntry).filter_by(english="utterly").one()
    old.translation = "adv. 用户自己的解释"
    old.completed, old.in_mistake_book, old.mistake_consec = 7, True, 2
    db.delete(db.query(AccumulationEntry).filter_by(english="completely").one())
    for entry in data["groups"][0]["entries"]:
        db.delete(db.query(AccumulationEntry).filter_by(english=entry["english"]).one())
    group = AccumulationGroup(name="用户自建")
    db.add(group)
    db.flush()
    service.save_entry(db, {"group_id": group.id, "item_type": "word",
        "english": "  SCRUTINIZE  ", "translation": "v. 用户自定细查"},
        commit=False, library="accumulation")
    db.delete(db.get(UserSetting, data["version"]))
    db.commit()
    seed_accumulation(db)
    assert db.query(AccumulationEntry).count() == 94
    assert db.query(AccumulationEntry).filter_by(normalized="scrutinize").count() == 1
    assert db.query(AccumulationEntry).filter_by(normalized="scrutinize").one().translation == "v. 用户自定细查"
    assert (old.translation, old.completed, old.in_mistake_book, old.mistake_consec) == ("adv. 用户自己的解释", 7, True, 2)
    assert not db.query(AccumulationEntry).filter_by(english="completely").count()
    erosion = db.query(AccumulationEntry).filter_by(english="erosion").one()
    assert erosion.translation.startswith("n.") and "erode" in erosion.source
    erosion.translation = "n. 用户补充侵蚀义"
    db.delete(db.query(AccumulationEntry).filter_by(english="turn out").one())
    db.commit()
    seed_accumulation(db)
    assert db.query(AccumulationEntry).count() == 93
    assert erosion.translation == "n. 用户补充侵蚀义"
    assert not db.query(AccumulationEntry).filter_by(english="turn out").count()


def test_november_second_batch_upgrade_and_replay(client_db):
    from scripts.seed_accumulation import LATEST_PATH
    _, db, _ = client_db
    batch = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    entries = batch["groups"][0]["entries"]
    assert len(entries) == 17
    assert batch["source_paragraph_range"] == [48, 63]
    assert sum(e["item_type"] == "word" for e in entries) == 15
    assert len(batch["source_sha256"]) == 64
    older = db.query(AccumulationEntry).filter_by(english="scrutinize").one()
    older.translation, older.completed, older.in_mistake_book = "v. 旧词用户释义", 5, True
    for entry in entries:
        db.delete(db.query(AccumulationEntry).filter_by(english=entry["english"]).one())
    db.delete(db.get(UserSetting, batch["version"]))
    group = AccumulationGroup(name="此前自行积累")
    db.add(group)
    db.flush()
    service.save_entry(db, {"group_id": group.id, "item_type": "word",
        "english": "  SWELL  ", "translation": "v. 用户释义"},
        commit=False, library="accumulation")
    db.commit()
    seed_accumulation(db)
    assert db.query(AccumulationEntry).count() == 95
    assert db.query(AccumulationEntry).filter_by(normalized="swell").count() == 1
    assert db.query(AccumulationEntry).filter_by(normalized="swell").one().translation == "v. 用户释义"
    assert (older.translation, older.completed, older.in_mistake_book) == ("v. 旧词用户释义", 5, True)
    assert db.query(AccumulationEntry).filter_by(english="resort to sth").one().item_type == "phrase"
    state = db.query(AccumulationEntry).filter_by(english="state").one()
    state.translation = "n. 用户补充状态义"
    state.completed = 3
    db.delete(db.query(AccumulationEntry).filter_by(english="culminate in sth").one())
    db.commit()
    seed_accumulation(db)
    assert db.query(AccumulationEntry).count() == 94
    assert state.translation == "n. 用户补充状态义" and state.completed == 3
    assert not db.query(AccumulationEntry).filter_by(english="culminate in sth").count()


def test_november_fourth_upgrade_preserves_edits_and_skips_duplicates(client_db):
    from scripts.seed_accumulation import NOVEMBER_FOURTH_PATH
    _, db, _ = client_db
    batch = json.loads(NOVEMBER_FOURTH_PATH.read_text(encoding="utf-8"))
    entries = batch["groups"][0]["entries"]
    assert len(entries) == 19 and batch["source_paragraph_range"] == [64, 82]
    assert all(e["item_type"] == "word" for e in entries)
    old = db.query(AccumulationEntry).filter_by(english="devise").one()
    old.translation, old.completed, old.in_mistake_book = "v. 用户旧释义", 6, True
    for entry in entries:
        db.delete(db.query(AccumulationEntry).filter_by(english=entry["english"]).one())
    db.delete(db.get(UserSetting, batch["version"]))
    group = AccumulationGroup(name="此前手动添加")
    db.add(group)
    db.flush()
    service.save_entry(db, {"group_id": group.id, "item_type": "word",
        "english": "  WARRANT  ", "translation": "v. 用户自定释义"},
        commit=False, library="accumulation")
    db.commit()
    seed_accumulation(db)
    assert db.query(AccumulationEntry).count() == 95
    assert db.query(AccumulationEntry).filter_by(normalized="warrant").count() == 1
    assert db.query(AccumulationEntry).filter_by(normalized="warrant").one().translation == "v. 用户自定释义"
    assert (old.translation, old.completed, old.in_mistake_book) == ("v. 用户旧释义", 6, True)
    beneficiary = db.query(AccumulationEntry).filter_by(english="beneficiary").one()
    beneficiary.translation, beneficiary.completed = "n. 用户补充受益人", 4
    db.delete(db.query(AccumulationEntry).filter_by(english="motive").one())
    db.commit()
    seed_accumulation(db)
    assert db.query(AccumulationEntry).count() == 94
    assert beneficiary.translation == "n. 用户补充受益人" and beneficiary.completed == 4
    assert not db.query(AccumulationEntry).filter_by(english="motive").count()
