"""错题本与选择题选项生成的测试（内存库）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Phrase, SrsCard, Word
from app.services import study
from app.services.srs import AGAIN, GOOD, HARD


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def seed_words(db, n=6):
    for i in range(n):
        db.add(Word(book="cet6", headword=f"word{i}", translation=f"释义{i}\nn. detail{i}", freq=10 - i))
    db.commit()


def add_card(db, word_id):
    c = SrsCard(item_type="word", item_id=word_id, book="cet6", status="new",
                due=date.today(), added_at=date.today())
    db.add(c)
    db.commit()
    return c


def test_answer_wrong_enters_mistake_book():
    db = make_db()
    seed_words(db)
    card = add_card(db, 1)
    study.answer(db, card.id, AGAIN)
    db.expire_all()
    c = db.get(SrsCard, card.id)
    assert c.in_mistake_book and c.mistake_consec == 0


def test_streak_three_correct_exits():
    db = make_db()
    seed_words(db)
    card = add_card(db, 1)
    study.answer(db, card.id, AGAIN)          # 答错 → 入本
    study.answer(db, card.id, GOOD)           # 连对 1
    study.answer(db, card.id, GOOD)           # 连对 2
    db.expire_all()
    c = db.get(SrsCard, card.id)
    assert c.in_mistake_book and c.mistake_consec == 2
    study.answer(db, card.id, GOOD)           # 连对 3 → 移出
    db.expire_all()
    c = db.get(SrsCard, card.id)
    assert not c.in_mistake_book and c.mistake_consec == 0


def test_streak_resets_on_wrong():
    db = make_db()
    seed_words(db)
    card = add_card(db, 1)
    study.answer(db, card.id, AGAIN)
    study.answer(db, card.id, GOOD)
    study.answer(db, card.id, GOOD)
    study.answer(db, card.id, HARD)           # 拼写首试错 → 计入错题、连对清零
    db.expire_all()
    c = db.get(SrsCard, card.id)
    assert c.in_mistake_book and c.mistake_consec == 0


def test_hard_counts_as_mistake():
    db = make_db()
    seed_words(db)
    card = add_card(db, 1)
    study.answer(db, card.id, HARD)           # 从未入本，拼写错也应进入错题本
    db.expire_all()
    c = db.get(SrsCard, card.id)
    assert c.in_mistake_book


def test_good_not_in_book_stays_out():
    db = make_db()
    seed_words(db)
    card = add_card(db, 1)
    study.answer(db, card.id, GOOD)
    db.expire_all()
    c = db.get(SrsCard, card.id)
    assert not c.in_mistake_book


def test_mistake_list_and_queue_source():
    db = make_db()
    seed_words(db)
    c1, c2 = add_card(db, 1), add_card(db, 2)
    study.answer(db, c1.id, AGAIN)
    q = study.study_queue(db, "word", "cet6", source="mistake")
    assert q["counts"]["review"] == 1
    assert q["review"][0]["card_id"] == c1.id
    lst = study.mistake_list(db, "word", "cet6")
    assert len(lst) == 1 and lst[0]["card_id"] == c1.id
    study.answer(db, c1.id, GOOD)
    study.answer(db, c1.id, GOOD)
    study.answer(db, c1.id, GOOD)
    assert study.mistake_list(db, "word", "cet6") == []


def test_queue_options_have_four_unique_with_answer():
    db = make_db()
    seed_words(db, 8)
    from app.models import UserSetting
    db.add(UserSetting(key="daily_new_words", value="1"))
    db.commit()
    add_card(db, 1)
    q = study.study_queue(db, "word", "cet6")
    cards = q["new"]
    assert len(cards) == 1
    p = cards[0]
    assert len(p["options"]) == 4
    assert len(set(p["options"])) == 4
    assert p["answer"] in p["options"]
    assert p["answer"] == study.first_line(p["translation"], 40)


def test_migration_adds_columns():
    """存量库（无新列）经 _migrate 后字段可用。"""
    import tempfile, os
    from sqlalchemy import text, create_engine as ce
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        eng = ce(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        with eng.begin() as conn:
            # 模拟旧表结构
            conn.execute(text("CREATE TABLE srs_cards (id INTEGER PRIMARY KEY, item_type VARCHAR(10))"))
            conn.execute(text("INSERT INTO srs_cards (id, item_type) VALUES (1, 'word')"))
        S = sessionmaker(bind=eng, expire_on_commit=False)
        db = S()
        from scripts.seed import _migrate
        _migrate(db)
        cols = [r[1] for r in db.execute(text("PRAGMA table_info(srs_cards)")).fetchall()]
        assert "in_mistake_book" in cols and "mistake_consec" in cols
        row = db.execute(text("SELECT in_mistake_book FROM srs_cards WHERE id=1")).fetchone()
        assert row[0] in (0, False, None)
        db.close()
        eng.dispose()
    finally:
        os.remove(path)
