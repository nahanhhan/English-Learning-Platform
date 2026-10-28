"""整理后的平时笔记仅导入一次，保留用户后续删改。"""
import json
from pathlib import Path

from app.models import AccumulationGroup, UserSetting
from app.services.classroom import ClassroomError, save_entry

INITIAL_PATH = Path(__file__).resolve().parent.parent / "data" / "accumulation_initial.json"


def seed_accumulation(db):
    data = json.loads(INITIAL_PATH.read_text(encoding="utf-8"))
    if db.get(UserSetting, data["version"]):
        return
    try:
        for source_group in data["groups"]:
            group = db.query(AccumulationGroup).filter_by(name=source_group["name"]).first()
            if group is None:
                group = AccumulationGroup(name=source_group["name"])
                db.add(group)
                db.flush()
            for entry in source_group["entries"]:
                try:
                    save_entry(db, {**entry, "group_id": group.id}, commit=False, library="accumulation")
                except ClassroomError as exc:
                    if exc.status != 409:
                        raise
        db.add(UserSetting(key=data["version"], value="1"))
        db.commit()
    except Exception:
        db.rollback()
        raise
