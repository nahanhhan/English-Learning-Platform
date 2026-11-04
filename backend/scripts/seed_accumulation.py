"""整理后的平时笔记仅导入一次，保留用户后续删改。"""
import json
from pathlib import Path

from app.models import AccumulationEntry, AccumulationGroup, UserSetting
from app.services.classroom import ClassroomError, normalize, save_entry

INITIAL_PATH = Path(__file__).resolve().parent.parent / "data" / "accumulation_initial.json"


UPDATE_PATH = INITIAL_PATH.with_name("accumulation_notes_20261101.json")
LATEST_PATH = INITIAL_PATH.with_name("accumulation_notes_20261102.json")
NOVEMBER_FOURTH_PATH = INITIAL_PATH.with_name("accumulation_notes_20261104.json")


def seed_accumulation(db):
    for path in (INITIAL_PATH, UPDATE_PATH, LATEST_PATH, NOVEMBER_FOURTH_PATH):
        _seed_batch(db, json.loads(path.read_text(encoding="utf-8")))


def _seed_batch(db, data):
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
                # 同一积累词库跨分组去重，保留既有释义和学习记录。
                if db.query(AccumulationEntry).filter_by(
                    item_type=entry["item_type"], normalized=normalize(entry["english"])
                ).first():
                    continue
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
