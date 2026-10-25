"""用户照片词汇一次性导入；删改后不在启动时恢复。"""
import json
from pathlib import Path

from app.models import ClassroomGroup, UserSetting
from app.services.classroom import save_entry


def seed_classroom(db):
    path = Path(__file__).resolve().parent.parent / "data" / "classroom_initial.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if db.get(UserSetting, data["version"]):
        return
    try:
        for source_group in data["groups"]:
            group = db.query(ClassroomGroup).filter_by(name=source_group["name"]).first()
            if group is None:
                group = ClassroomGroup(name=source_group["name"])
                db.add(group)
                db.flush()
            for key, kind in (("words", "word"), ("phrases", "phrase")):
                for english, translation in source_group[key]:
                    from app.services.classroom import ClassroomError
                    try:
                        save_entry(db, {"group_id": group.id, "item_type": kind,
                                        "english": english, "translation": translation,
                                        "source": source_group["source"]}, commit=False)
                    except ClassroomError as exc:
                        if exc.status != 409:
                            raise
        db.add(UserSetting(key=data["version"], value="1"))
        db.commit()
    except Exception:
        db.rollback()
        raise
