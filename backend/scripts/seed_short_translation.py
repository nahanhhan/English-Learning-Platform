"""按稳定题号增量添加短句题目，不覆盖既有题面和作答。"""
import json
from pathlib import Path
from app.models import ShortQuestion

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "short_translations.json"


def seed_short_translation(db):
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    added = 0
    for question in data['questions']:
        if db.get(ShortQuestion, question['id']) is None:
            db.add(ShortQuestion(id=question['id'], topic=question['topic'], title=question['title'],
                                 data_json=json.dumps(question, ensure_ascii=False), batch=data['batch']))
            added += 1
    db.commit()
    return added
