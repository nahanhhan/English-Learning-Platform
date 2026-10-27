"""课内复习的事务、恢复、导入与隔离测试，均使用临时数据库。"""
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import Base, get_db
from app.models import (ClassroomEntry as Entry, ClassroomGroup as Group,
                        ClassroomSession as Round, ClassroomSessionItem as Question, Word)
from app.routers.classroom import ImportBody, confirm_import, router
from app.services import classroom as c
from app.services.classroom_import import extract_file, parse_text
from scripts.seed_classroom import seed_classroom


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'classroom.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    yield db, factory
    db.close()
    engine.dispose()


def seed(db, kind="word", n=4):
    group = Group(name=f"课堂 {uuid.uuid4().hex[:6]}")
    db.add(group)
    db.commit()
    for i in range(n):
        c.save_entry(db, {"group_id": group.id, "english": f"word{i}" if kind == "word" else f"take note{i}",
                          "translation": f"中文释义{i}", "item_type": kind})
    return group


def act(db, session, action, value="", request_id=None):
    return c.act(db, session["id"], session["current"]["question_id"], session["version"],
                 request_id or str(uuid.uuid4()), action, value)


def finish_one(db, session, wrong_choice=False, wrong_spell=False):
    question = session["current"]
    choice = next(o for o in question["options"] if o != question["translation"]) if wrong_choice else question["translation"]
    session = act(db, session, "choice", choice)
    if wrong_spell:
        session = act(db, session, "spell", "incorrect")
    return act(db, session, "spell", question["english"])


@pytest.mark.parametrize("kind", ["word", "phrase"])
def test_round_flow_and_phrase_spelling(database, kind):
    db, _ = database
    group = seed(db, kind)
    session = c.start(db, group.id, kind)
    assert session["total"] == 4
    assert len(session["current"]["options"]) == 4
    session = finish_one(db, session)
    assert session["current"]["stage"] == "done"
    assert session["completed"] == session["correct"] == 1
    session = act(db, session, "next")
    assert session["current"]["stage"] == "choice"


@pytest.mark.parametrize("wrong_choice,wrong_spell", [(True, False), (False, True), (True, True)])
def test_wrong_enters_immediately_and_streak(database, wrong_choice, wrong_spell):
    db, _ = database
    group = seed(db)
    session = c.start(db, group.id)
    entry_id = session["current"]["id"]
    question = session["current"]
    option = next(o for o in question["options"] if o != question["translation"]) if wrong_choice else question["translation"]
    session = act(db, session, "choice", option)
    if wrong_choice:
        assert db.get(Entry, entry_id).in_mistake_book
    if wrong_spell:
        session = act(db, session, "spell", "wrong")
        assert db.get(Entry, entry_id).in_mistake_book
        assert session["current"]["spell_wrong"]
    session = act(db, session, "spell", question["english"])
    assert session["current"]["rating"] == ("again" if wrong_choice else "hard")
    for streak in (1, 2):
        session = c.start(db, group.id, source="mistake", restart=True)
        session = finish_one(db, session)
        assert session["current"]["mistake_consec"] == streak
    session = c.start(db, group.id, source="mistake", restart=True)
    session = finish_one(db, session, wrong_spell=True)
    assert session["current"]["mistake_consec"] == 0
    for _ in range(3):
        session = finish_one(db, c.start(db, group.id, source="mistake", restart=True))
    assert not db.get(Entry, entry_id).in_mistake_book
    assert session["current"]["mistake_consec"] == 0


def test_resume_each_stage_across_connections(database):
    db, factory = database
    group = seed(db)
    session = c.start(db, group.id)
    original = session["current"]
    db.close()
    with factory() as reopened:
        session = c.start(reopened, group.id)
        assert session["current"]["question_id"] == original["question_id"]
        assert session["current"]["options"] == original["options"]
        session = act(reopened, session, "choice", original["translation"])
        session = act(reopened, session, "spell", "misspelled")
    with factory() as reopened:
        session = c.start(reopened, group.id)
        assert session["current"]["stage"] == "spell" and session["current"]["spell_wrong"]
        session = act(reopened, session, "spell", original["english"])
    with factory() as reopened:
        session = c.start(reopened, group.id)
        assert session["current"]["stage"] == "done" and session["current"]["rating"] == "hard"
        session = act(reopened, session, "next")
        assert session["current"]["question_id"] != original["question_id"]


def test_retries_and_stale_requests_do_not_increment(database):
    db, _ = database
    group = seed(db)
    session = c.start(db, group.id)
    session = act(db, session, "choice", session["current"]["translation"])
    previous = session
    request_id = "same-request"
    session = act(db, previous, "spell", session["current"]["english"], request_id)
    session = act(db, previous, "spell", session["current"]["english"], request_id)
    assert db.get(Entry, session["current"]["id"]).completed == 1
    with pytest.raises(c.ClassroomError, match="进度已更新"):
        act(db, previous, "spell", previous["current"]["english"])
    session = act(db, session, "next")
    retried = act(db, previous, "spell", previous["current"]["english"], request_id)
    assert retried["current"]["question_id"] == session["current"]["question_id"]
    assert retried["completed"] == 1


def test_scopes_snapshots_and_deleted_entries(database):
    db, _ = database
    group = seed(db)
    other = seed(db, "phrase")
    first = c.start(db, group.id)
    all_groups = c.start(db)
    assert all_groups["total"] == 8 and first["total"] == 4
    c.start(db, other.id, "phrase")
    entry = db.get(Entry, first["current"]["id"])
    c.save_entry(db, {"group_id": group.id, "english": "changed", "translation": "已修改", "item_type": "word"}, entry.id)
    assert c.start(db, group.id)["current"]["english"] == first["current"]["english"]
    db.delete(entry)
    db.commit()
    resumed = c.start(db, group.id)
    assert resumed["total"] == 3
    assert resumed["current"]["question_id"] != first["current"]["question_id"]
    assert c.start(db, other.id, "phrase")["total"] == 4


def test_finish_round_without_requeue_and_restart(database):
    db, _ = database
    group = seed(db)
    session = c.start(db, group.id)
    first_id = session["id"]
    for _ in range(4):
        session = finish_one(db, session, wrong_spell=True)
        session = act(db, session, "next")
    assert session["finished"] and session["total"] == session["completed"] == 4
    assert session["correct"] == 0
    assert c.start(db, group.id)["finished"]
    assert c.start(db, group.id, restart=True)["id"] != first_id


def test_normalize_spelling_and_punctuation(database):
    assert c.normalize("  Take   Note ") == "take note"
    assert c.normalize("rear-view mirror") != c.normalize("rear view mirror")
    assert c.normalize("one's") != c.normalize("ones")
    db, _ = database
    group = seed(db, "phrase")
    session = c.start(db, group.id)
    session = act(db, session, "choice", session["current"]["translation"])
    spelling = "  " + "   ".join(session["current"]["english"].upper().split()) + " "
    session = act(db, session, "spell", spelling)
    assert session["current"]["rating"] == "good"


def test_fallback_excludes_same_english_and_duplicate_meanings(database):
    db, _ = database
    group = seed(db, n=1)
    with pytest.raises(c.ClassroomError, match="干扰项"):
        c.start(db, group.id)
    db.add_all([Word(book="cet6", headword="word0", translation="另一种释义"),
                Word(book="cet6", headword="apple", translation="苹果"),
                Word(book="kaoyan", headword="apple", translation="苹果")])
    db.commit()
    session = c.start(db, group.id)
    options = session["current"]["options"]
    assert len(options) == len(set(options)) == 2
    assert "另一种释义" not in options


def test_import_dedup_is_transactional_and_preserves_progress(database):
    db, _ = database
    group = seed(db)
    entry = db.query(Entry).first()
    entry.in_mistake_book = True
    entry.mistake_consec = 2
    db.commit()
    result = confirm_import(ImportBody(rows=[{"group_id": group.id, "item_type": "word", "english": " WORD0 ", "translation": "新释义"}]), db)
    assert result == {"added": 0, "skipped": 1}
    assert entry.translation == "中文释义0" and entry.mistake_consec == 2
    with pytest.raises(c.ClassroomError):
        confirm_import(ImportBody(rows=[
            {"group_id": group.id, "item_type": "word", "english": "new", "translation": "新词"},
            {"group_id": group.id, "item_type": "word", "english": "invalid", "translation": ""}]), db)
    assert not db.query(Entry).filter_by(english="new").count()
    other = seed(db, n=0)
    result = confirm_import(ImportBody(rows=[{"group_id": other.id, "item_type": "word", "english": "word0", "translation": "其他课"}]), db)
    assert result["added"] == 1


def docx_bytes(xml):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return stream.getvalue()


def test_text_and_word_paragraph_table_preview():
    rows = parse_text("reluctant | 不愿意的\nreason with\t跟某人讲理\n只有中文\nunknown")
    assert rows[0]["english"] == "reluctant"
    assert rows[1]["item_type"] == "phrase"
    assert rows[2]["english"] == "" and rows[3]["translation"] == ""
    xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:p><w:r><w:t>reluctant | 不愿意的</w:t></w:r></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>reason with</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>跟某人讲理</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''
    result = extract_file(docx_bytes(xml), "课堂.docx")
    assert len(result["rows"]) == 2
    assert result["rows"][1]["english"] == "reason with"
    assert result["rows"][1]["translation"] == "跟某人讲理"
    with pytest.raises(c.ClassroomError, match="另存为"):
        extract_file(b"abc", "课堂.doc")
    with pytest.raises(c.ClassroomError, match="无法解析"):
        extract_file(b"invalid", "课堂.docx")


def test_pdf_text_and_scanned_preview(monkeypatch):
    import pymupdf
    import app.services.classroom_import as parser
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 40), "reluctant", fontsize=15)
    page.insert_text((115, 40), "不愿意的", fontname="china-s", fontsize=15)
    result = extract_file(doc.tobytes(), "词表.pdf")
    assert result["rows"][0]["english"] == "reluctant"
    assert result["rows"][0]["translation"] == "不愿意的"
    blank = pymupdf.open()
    blank.new_page()
    monkeypatch.setattr(parser, "ocr_image", lambda image: "reason with | 跟某人讲理")
    result = extract_file(blank.tobytes(), "扫描.pdf")
    assert result["rows"][0]["item_type"] == "phrase"
    doc.close(); blank.close()


def test_photo_seed_only_two_articles_is_idempotent(database):
    db, _ = database
    seed_classroom(db)
    names = {g.name for g in db.query(Group)}
    assert names == {"We are all dying", "Cultural childhoods"}
    count = db.query(Entry).count()
    assert count > 100
    english = {e.english for e in db.query(Entry)}
    assert {"what the hell", "end up", "Grand Canyon", "Santa Claus"}.isdisjoint(english)
    seed_classroom(db)
    assert db.query(Entry).count() == count
    removed = db.query(Entry).first()
    db.delete(removed); db.commit()
    seed_classroom(db)
    assert db.query(Entry).count() == count - 1


def test_ocr_pairs_boxes_on_same_line(monkeypatch):
    import app.services.classroom_import as parser
    boxes = [
        ([[0, 0], [90, 0], [90, 20], [0, 20]], "reluctant", .99),
        ([[130, 1], [230, 1], [230, 21], [130, 21]], "不愿意的", .99),
        ([[0, 50], [90, 50], [90, 70], [0, 70]], "reason with", .99),
        ([[130, 51], [230, 51], [230, 71], [130, 71]], "跟某人讲理", .99),
    ]
    monkeypatch.setattr(parser, "_ocr", lambda image: (boxes, None))
    rows = parser.parse_text(parser.ocr_image(None))
    assert [(row["english"], row["translation"]) for row in rows] == [
        ("reluctant", "不愿意的"), ("reason with", "跟某人讲理")]


def test_phonetics_backfill_old_snapshot_without_resetting_progress(database):
    db, _ = database
    seed_classroom(db)
    session = c.start(db, item_type="word")
    original_id = session["current"]["question_id"]
    assert session["current"]["phonetic_us"]
    question = db.get(Question, original_id)
    snapshot = json.loads(question.snapshot)
    snapshot.pop("phonetic_us", None)
    question.snapshot = json.dumps(snapshot)
    db.commit()
    session = act(db, session, "choice", session["current"]["translation"])
    resumed = c.start(db, item_type="word")
    assert resumed["current"]["question_id"] == original_id
    assert resumed["current"]["stage"] == "spell"
    assert resumed["current"]["phonetic_us"]


def test_search_before_pagination_and_snapshot_survives_failed_restart(database):
    db, _ = database
    group = seed(db, n=35)
    assert c.filtered(db, group.id, search="word34").count() == 1
    assert c.filtered(db, group.id, search="word34").first().english == "word34"
    session = c.start(db, group.id)
    # 删除其他词，当前轮次仍能查看；重新出题失败不能破坏保存的轮次。
    db.query(Entry).filter(Entry.id != session["current"]["id"]).delete()
    db.commit()
    with pytest.raises(c.ClassroomError, match="干扰项"):
        c.start(db, group.id, restart=True)
    assert c.start(db, group.id)["id"] == session["id"]


def test_http_validation_and_preview_without_writes(database):
    db, factory = database
    app = FastAPI()
    app.include_router(router)
    def dependency():
        with factory() as connection:
            yield connection
    app.dependency_overrides[get_db] = dependency
    @app.exception_handler(c.ClassroomError)
    async def error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})
    with TestClient(app) as client:
        assert client.get("/api/classroom/sessions/current").json() is None
        assert client.get("/api/classroom/entries?item_type=invalid").status_code == 422
        result = client.post("/api/classroom/imports/text", json={"text": "apple | 苹果"})
        assert result.status_code == 200 and result.json()["rows"][0]["english"] == "apple"
        assert db.query(Entry).count() == 0
        assert client.post("/api/classroom/imports/file?filename=old.doc", content=b"old").status_code == 400
        assert client.post("/api/classroom/groups", json={"name": "Unit 1"}).status_code == 200
        assert client.post("/api/classroom/groups", json={"name": "Unit 1"}).status_code == 409
        assert client.post("/api/classroom/sessions", json={}).status_code == 400


@pytest.mark.parametrize("kind", ["all", "word", "phrase"])
@pytest.mark.parametrize("source", ["normal", "mistake"])
def test_new_rounds_shuffle_scoped_entries_and_option_positions(database, monkeypatch, kind, source):
    db, _ = database
    group = seed(db)
    for i in range(4):
        c.save_entry(db, {"group_id": group.id, "english": f"take note{i}",
                          "translation": f"短语释义{i}", "item_type": "phrase"})
    other = seed(db)
    for entry in db.query(Entry):
        entry.in_mistake_book = entry.id % 2 == 0
    db.commit()
    expected = [e.id for e in c.filtered(db, group.id, kind, mistakes=source == "mistake")]
    round_number = 0

    def controlled_shuffle(values):
        # 固定抽样结果，避免“随机后碰巧相同”导致测试偶发失败。
        nonlocal round_number
        if values and isinstance(values[0], Entry):
            round_number += 1
        if values and isinstance(values[0], tuple):
            values.reverse()
        elif values:
            shift = round_number % len(values)
            values[:] = values[shift:] + values[:shift]

    monkeypatch.setattr(c.random, "shuffle", controlled_shuffle)

    def saved_questions(session):
        rows = db.query(Question).filter_by(session_id=session["id"]).order_by(Question.position).all()
        assert [q.position for q in rows] == list(range(len(expected)))
        assert {q.entry_id for q in rows} == set(expected)
        assert len(rows) == len(set(q.entry_id for q in rows))
        assert not any(db.get(Entry, q.entry_id).group_id == other.id for q in rows)
        answer_positions = {}
        for question in rows:
            options = json.loads(question.options)
            answer = json.loads(question.snapshot)["translation"]
            assert len(options) == len(set(options)) == 4
            assert options.count(answer) == 1
            answer_positions[question.entry_id] = options.index(answer)
        return [q.entry_id for q in rows], answer_positions

    first = c.start(db, group.id, kind, source)
    first_order, first_positions = saved_questions(first)
    assert first_order == expected[1:] + expected[:1]
    second = c.start(db, group.id, kind, source, restart=True)
    second_order, second_positions = saved_questions(second)
    assert second["id"] != first["id"]
    assert second_order == expected[2:] + expected[:2]
    assert second_order != first_order
    assert all(first_positions[key] != second_positions[key] for key in expected)
    assert round_number == 2
    # 浏览列表仍按原始词条顺序展示。
    assert [e.id for e in c.filtered(db, group.id, kind, mistakes=source == "mistake")] == expected


def test_randomized_round_resume_preserves_all_questions_and_spelling(database, monkeypatch):
    db, factory = database
    group = seed(db)
    group_id = group.id
    rng = c.random.Random(2026)
    monkeypatch.setattr(c.random, "shuffle", rng.shuffle)
    session = c.start(db, group_id)
    session = act(db, session, "choice", session["current"]["translation"])
    session = act(db, session, "spell", "incorrect")

    def saved_questions(connection):
        return [(q.id, q.entry_id, q.position, q.options, q.snapshot)
                for q in connection.query(Question).filter_by(session_id=session["id"]).order_by(Question.position)]

    original = saved_questions(db)
    db.close()

    def must_not_shuffle(values):
        raise AssertionError("继续已有轮次不应打乱题目或选项")

    monkeypatch.setattr(c.random, "shuffle", must_not_shuffle)
    with factory() as reopened:
        resumed = c.start(reopened, group_id)
        assert resumed["id"] == session["id"]
        assert resumed["version"] == session["version"]
        assert resumed["current"] == session["current"]
        assert resumed["current"]["stage"] == "spell"
        assert resumed["current"]["spell_wrong"]
        assert saved_questions(reopened) == original
