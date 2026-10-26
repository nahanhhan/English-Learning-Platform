"""词性来源、现有词库完整性和各学习入口的兼容性。"""
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import Base, get_db
from app.models import (ClassroomGroup, ClassroomSessionItem, Phrase, SrsCard, Word)
from app.routers.vocab import router as vocab_router
from app.routers.classroom import router as classroom_router
from app.services import classroom, study
from app.services.parts_of_speech import DATA_DIR, extract_parts_of_speech, parts_of_speech


@pytest.mark.parametrize("text,expected", [
    ("n. 名词\\nvt. 动作\\nvi. 动作", "n. / vt. / vi."),
    ("a. 形容词；ad. 副词；adj. 同一词性", "adj. / adv."),
    ("n. 名词; v. 动词", "n. / v."),
    ("n. / vt. / vi.", "n. / vt. / vi."),
    ("[医] adj. 形容词", "adj."),
    ("n.名词", "n."),
    ("中文释义，如 sb. / sth. 占位词", ""),
    ("a normal English sentence", ""),
    ("I am learning", ""),
    ("", ""),
])
def test_explicit_markers_are_normalized_without_guessing(text, expected):
    assert extract_parts_of_speech(text) == expected


def test_definition_fallback_and_custom_translation_priority():
    assert parts_of_speech("rainforest", "雨林", "n a forest with heavy annual rainfall") == "n."
    assert parts_of_speech("crippling", "", "s. that cripples or disables") == "adj."
    assert parts_of_speech("  BEARER ", "带信者") == "n."
    assert parts_of_speech("triple", "adj. 三重的") == "adj."
    assert parts_of_speech("classroomunknownzzzzz", "不明词") == ""


def test_all_shipped_words_and_classroom_words_have_parts_of_speech():
    books = json.loads((DATA_DIR / "words.json").read_text(encoding="utf-8"))
    missing = [w["headword"] for words in books.values() for w in words
               if not parts_of_speech(w["headword"], w["translation"], w.get("definition", ""))]
    initial = json.loads((DATA_DIR / "classroom_initial.json").read_text(encoding="utf-8"))
    missing += [english for group in initial["groups"] for english, translation in group["words"]
                if not parts_of_speech(english, translation)]
    assert missing == []


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pos.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    yield db
    db.close()
    engine.dispose()


def test_vocab_api_has_pos_in_queue_answer_mistakes_browse_and_quiz(database):
    db = database
    db.add(Word(book="custom", headword="bearer", translation="带信者"))
    db.add(Phrase(book="custom", text="look up", translation="查阅"))
    db.commit()
    db.add(SrsCard(item_type="phrase", item_id=1, book="custom"))
    db.commit()
    app = FastAPI()
    app.include_router(vocab_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        created = client.post("/api/vocab/custom", json={"headword": "testwordzz", "translation": "adj. 测试词"})
        assert created.status_code == 200
        queue = client.get("/api/vocab/queue?book=custom").json()
        cards = queue["review"] + queue["new"]
        assert {c["headword"]: c["part_of_speech"] for c in cards} == {"bearer": "n.", "testwordzz": "adj."}
        card = next(c for c in cards if c["headword"] == "bearer")
        answer = client.post("/api/vocab/answer", json={"card_id": card["card_id"], "rating": "again"})
        assert answer.json()["part_of_speech"] == "n."
        assert client.get("/api/vocab/mistakes?book=custom").json()[0]["part_of_speech"] == "n."
        assert all(c["part_of_speech"] for c in client.get("/api/vocab/browse?book=custom").json()["items"])
        quiz = client.get("/api/vocab/quiz?book=custom").json()
        assert {q["front"]: q["part_of_speech"] for q in quiz} == {"bearer": "n.", "testwordzz": "adj."}
        assert study.study_queue(db, "phrase", "custom")["new"][0].get("part_of_speech", "") == ""


def test_classroom_api_and_legacy_snapshot_keep_progress(database):
    db = database
    group = ClassroomGroup(name="词性课")
    db.add(group)
    db.commit()
    app = FastAPI()
    app.include_router(classroom_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        for english, translation, kind in [("bearer", "带信者", "word"), ("wisely", "明智地", "word"),
                                            ("reason with", "讲理", "phrase")]:
            response = client.post("/api/classroom/entries", json={"group_id": group.id,
                "english": english, "translation": translation, "item_type": kind})
            assert response.status_code == 200
            assert response.json()["part_of_speech"] == ("n." if english == "bearer" else "adv." if english == "wisely" else "")
        listed = client.get("/api/classroom/entries?item_type=word").json()["items"]
        assert all(e["part_of_speech"] for e in listed)
        session = classroom.start(db, group.id, "word")
        current = session["current"]
        session = classroom.act(db, session["id"], current["question_id"], session["version"],
                                "choose-pos", "choice", current["translation"])
        question = db.get(ClassroomSessionItem, current["question_id"])
        legacy = json.loads(question.snapshot)
        legacy.pop("part_of_speech")
        question.snapshot = json.dumps(legacy)
        db.commit()
        resumed = client.get(f"/api/classroom/sessions/current?group_id={group.id}&item_type=word").json()
        assert resumed["version"] == session["version"]
        assert resumed["current"]["part_of_speech"] == current["part_of_speech"]
        assert resumed["current"]["stage"] == "spell"
        assert resumed["current"]["options"] == current["options"]
        assert resumed["current"]["question_id"] == current["question_id"]
        assert resumed["current"]["picked"] == current["translation"]
