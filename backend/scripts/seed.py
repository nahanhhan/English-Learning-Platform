"""首次启动时把 questions.json / words.json / phrases.json 导入 SQLite（幂等）。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Phrase, Question, UserSetting, Word  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _count(db, model) -> int:
    return db.query(model).count()


def _migrate(db):
    """存量库增量迁移：为 srs_cards 补齐错题本字段。"""
    from sqlalchemy import text
    cols = [r[1] for r in db.execute(text("PRAGMA table_info(srs_cards)")).fetchall()]
    if not cols:
        return  # 表尚不存在，create_all 会带全字段建表
    if "in_mistake_book" not in cols:
        db.execute(text("ALTER TABLE srs_cards ADD COLUMN in_mistake_book BOOLEAN DEFAULT 0"))
    if "mistake_consec" not in cols:
        db.execute(text("ALTER TABLE srs_cards ADD COLUMN mistake_consec INTEGER DEFAULT 0"))
    db.commit()


def ensure_seeded(force: bool = False):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        _migrate(db)
        if force:
            db.query(Question).delete()
            db.query(Word).filter(Word.book != "custom").delete()
            db.query(Phrase).filter(Phrase.book != "custom").delete()
            db.commit()

        # 题库
        if _count(db, Question) == 0:
            path = os.path.join(DATA_DIR, "questions.json")
            if os.path.exists(path):
                items = json.load(open(path, encoding="utf-8"))
                for it in items:
                    db.add(Question(
                        exam_type=it["exam_type"], year=it["year"], month=it.get("month", 0),
                        set_no=it.get("set_no", 1), q_type=it["q_type"], title=it.get("title", ""),
                        prompt=it.get("prompt", ""), source_text=it.get("source_text", ""),
                        chart_image=it.get("chart_image", ""), source_file=it.get("source_file", ""),
                        notes=it.get("notes", ""),
                    ))
                db.commit()
                print(f"题库导入：{len(items)} 题")

        # 对存量题目增量更正，保留主键、练习次数与提交时的原文快照。
        from scripts.question_review import sync_reviewed_questions
        corrected = sync_reviewed_questions(db)
        if corrected:
            db.commit()
            print(f"题库核对更正：{corrected} 题（保留原 ID 与练习记录）")

        # 词库
        wpath = os.path.join(DATA_DIR, "words.json")
        if _count(db, Word) == 0 and os.path.exists(wpath):
            data = json.load(open(wpath, encoding="utf-8"))
            n = 0
            for book, words in data.items():
                for w in words:
                    db.add(Word(book=book, headword=w["headword"],
                                phonetic_us=w.get("phonetic_us", ""),
                                translation=w.get("translation", ""),
                                definition=w.get("definition", ""),
                                tags=w.get("tags", ""), freq=w.get("freq", 0)))
                    n += 1
            db.commit()
            print(f"词库导入：{n} 词")

        ppath = os.path.join(DATA_DIR, "phrases.json")
        if _count(db, Phrase) == 0 and os.path.exists(ppath):
            phrases = json.load(open(ppath, encoding="utf-8"))
            for p in phrases:
                db.add(Phrase(book="exam", text=p["text"],
                              translation=p.get("translation", ""),
                              note=p.get("note", "")))
            db.commit()
            print(f"短语导入：{len(phrases)} 条")

        # 默认设置
        defaults = {"daily_new_words": "20", "daily_new_phrases": "10", "mock_mode": "0"}
        for k, v in defaults.items():
            if not db.get(UserSetting, k):
                db.add(UserSetting(key=k, value=v))
        db.commit()
        from scripts.seed_classroom import seed_classroom
        seed_classroom(db)
        from scripts.seed_accumulation import seed_accumulation
        seed_accumulation(db)
    finally:
        db.close()


if __name__ == "__main__":
    force = "--force" in sys.argv
    ensure_seeded(force=force)
    print("seed 完成")
