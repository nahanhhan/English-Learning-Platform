"""课内与平时积累共用的持久化练习。每次提交在同一事务内推进阶段和维护错题。"""
import json
import random
import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import (ClassroomEntry as Entry, ClassroomGroup as Group,
                      ClassroomSession as Round, ClassroomSessionItem as Question,
                      AccumulationEntry, AccumulationGroup, AccumulationSession, AccumulationSessionItem,
                      Phrase, Word)
from .study import MISTAKE_EXIT_STREAK
from .phonetics import american_ipa
from .parts_of_speech import parts_of_speech


class ClassroomError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def library_models(library="classroom"):
    if library == "classroom":
        return Entry, Group, Round, Question
    if library == "accumulation":
        return AccumulationEntry, AccumulationGroup, AccumulationSession, AccumulationSessionItem
    raise ValueError("无效词库")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def entry_payload(db, entry, *, library="classroom"):
    _, Group, _, _ = library_models(library)
    group = db.get(Group, entry.group_id)
    return {"id": entry.id, "group_id": entry.group_id,
            "group_name": group.name if group else "已删除分组", "item_type": entry.item_type,
            "english": entry.english, "translation": entry.translation, "source": entry.source,
            "part_of_speech": parts_of_speech(entry.english, entry.translation) if entry.item_type == "word" else "",
            "phonetic_us": american_ipa(entry.english) if entry.item_type == "word" else "",
            "in_mistake_book": entry.in_mistake_book,
            "mistake_consec": entry.mistake_consec, "completed": entry.completed}


def filtered(db, group_id=None, item_type="all", search="", mistakes=False, *, library="classroom"):
    Entry, _, _, _ = library_models(library)
    q = db.query(Entry)
    if group_id is not None:
        q = q.filter(Entry.group_id == group_id)
    if item_type != "all":
        q = q.filter(Entry.item_type == item_type)
    if mistakes:
        q = q.filter(Entry.in_mistake_book.is_(True))
    if search.strip():
        term = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        q = q.filter(Entry.english.ilike(term, escape="\\") | Entry.translation.ilike(term, escape="\\"))
    return q.order_by(Entry.id)


def save_entry(db, data, entry_id=None, commit=True, *, library="classroom"):
    Entry, Group, _, _ = library_models(library)
    if not db.get(Group, data["group_id"]):
        raise ClassroomError("请先选择有效分组")
    english = re.sub(r"\s+", " ", data["english"].strip())
    translation = data["translation"].strip().replace("\\n", "\n")
    if not english or not re.search(r"[A-Za-z]", english) or not translation:
        raise ClassroomError("请填写英文和中文释义")
    if data["item_type"] not in ("word", "phrase"):
        raise ClassroomError("词条类型无效")
    key = normalize(english)
    duplicate = db.query(Entry).filter_by(group_id=data["group_id"], item_type=data["item_type"], normalized=key).first()
    if duplicate and duplicate.id != entry_id:
        raise ClassroomError("该分组已有相同类型的英文词条", 409)
    entry = db.get(Entry, entry_id) if entry_id else Entry()
    if entry is None:
        raise ClassroomError("词条不存在", 404)
    for field, value in {"group_id": data["group_id"], "item_type": data["item_type"],
                         "english": english, "normalized": key, "translation": translation,
                         "source": data.get("source", "")}.items():
        setattr(entry, field, value)
    db.add(entry)
    db.flush()
    if commit:
        db.commit()
    return entry


def scope_key(group_id, item_type, source):
    return f"{group_id or 'all'}:{item_type}:{source}"


def _options(entry, classroom_pool, fallback):
    correct = entry.translation.strip()
    seen = {normalize(correct)}
    options = [correct]
    for pool in (classroom_pool, fallback):
        candidates = list(pool)
        random.shuffle(candidates)
        # 同一个英文在任何分组/词库的其他释义也不能成为干扰项。
        excluded = {normalize(t) for en, t in classroom_pool + fallback if normalize(en) == entry.normalized}
        for english, meaning in candidates:
            meaning = meaning.strip().replace("\\n", "\n")
            key = normalize(meaning)
            if not meaning or key in seen or key in excluded or normalize(english) == entry.normalized:
                continue
            options.append(meaning)
            seen.add(key)
            if len(options) == 4:
                break
        if len(options) == 4:
            break
    if len(options) < 2:
        raise ClassroomError(f"“{entry.english}”缺少不同释义的干扰项，请先补充同类型词汇")
    random.shuffle(options)
    return options


def start(db, group_id=None, item_type="all", source="normal", restart=False, *, library="classroom"):
    Entry, _, Round, Question = library_models(library)
    scope = scope_key(group_id, item_type, source)
    old = db.query(Round).filter_by(scope=scope).first()
    if old and not restart:
        return session_payload(db, old, library=library)
    entries = filtered(db, group_id, item_type, mistakes=source == "mistake", library=library).all()
    if not entries:
        raise ClassroomError("当前范围没有错题" if source == "mistake" else "当前范围还没有词汇，请先添加或导入")
    # 只在创建新轮次时打乱；题序和选项均保存，恢复进度时保持不变。
    random.shuffle(entries)
    pools = {}
    for kind in {e.item_type for e in entries}:
        local = [(e.english, e.translation) for e in db.query(Entry).filter_by(item_type=kind).all()]
        if kind == "word":
            fallback = [(en, (t or "").replace("\\n", "\n").split("\n")[0])
                        for en, t in db.query(Word.headword, Word.translation).all()]
        else:
            fallback = [(en, (t or "").replace("\\n", "\n").split("\n")[0])
                        for en, t in db.query(Phrase.text, Phrase.translation).all()]
        pools[kind] = local, fallback
    # 先完整验证再替换上一轮；出题失败不能丢失已有进度。
    snapshots = [(e, _options(e, *pools[e.item_type])) for e in entries]
    if old:
        db.query(Question).filter_by(session_id=old.id).delete()
        db.delete(old)
        db.flush()
    session = Round(scope=scope, source=source)
    db.add(session)
    db.flush()
    for position, (entry, options) in enumerate(snapshots):
        db.add(Question(session_id=session.id, entry_id=entry.id, position=position,
                        snapshot=json.dumps(entry_payload(db, entry, library=library), ensure_ascii=False),
                        options=json.dumps(options, ensure_ascii=False)))
    db.commit()
    return session_payload(db, session, library=library)


def session_payload(db, session, *, library="classroom"):
    Entry, _, _, Question = library_models(library)
    questions = db.query(Question).filter_by(session_id=session.id).order_by(Question.position).all()
    alive = set(db.scalars(select(Entry.id)).all())
    # 删除只跳过未完成题；完成结果继续留在本轮统计中。
    for question in questions:
        if question.entry_id not in alive and question.stage not in ("done", "skipped"):
            question.stage = "skipped"
    while session.cursor < len(questions) and questions[session.cursor].stage == "skipped":
        session.cursor += 1
    db.commit()
    current = questions[session.cursor] if session.cursor < len(questions) else None
    valid = [q for q in questions if q.stage != "skipped"]
    done = [q for q in valid if q.stage == "done"]
    payload = {"id": session.id, "version": session.version, "source": session.source,
               "finished": current is None, "total": len(valid), "completed": len(done),
               "correct": sum(q.rating == "good" for q in done),
               "updated_at": session.updated_at.isoformat(), "current": None}
    if current:
        snapshot = json.loads(current.snapshot)
        if snapshot["item_type"] == "word" and not snapshot.get("part_of_speech"):
            snapshot["part_of_speech"] = parts_of_speech(snapshot["english"], snapshot["translation"])
        # 兼容音标功能加入前已经保存的轮次，不重建题目或改变拼写阶段。
        if snapshot["item_type"] == "word" and not snapshot.get("phonetic_us"):
            snapshot["phonetic_us"] = american_ipa(snapshot["english"])
        entry = db.get(Entry, current.entry_id)
        payload["current"] = {**snapshot, "question_id": current.id, "stage": current.stage,
                              "options": json.loads(current.options), "picked": current.picked,
                              "spell_wrong": current.spell_wrong, "rating": current.rating,
                              "in_mistake_book": bool(entry and entry.in_mistake_book),
                              "mistake_consec": entry.mistake_consec if entry else 0}
    return payload


def mark_wrong(entry):
    entry.in_mistake_book = True
    entry.mistake_consec = 0


def act(db: Session, session_id: int, question_id: int, version: int,
        request_id: str, action: str, value: str = "", *, library="classroom"):
    Entry, _, Round, Question = library_models(library)
    session = db.get(Round, session_id)
    if session is None:
        raise ClassroomError("这一轮已被重新开始，请返回复习页", 404)
    receipts = json.loads(session.receipts)
    if request_id in receipts:
        return session_payload(db, session, library=library)
    # 数据库条件更新取得写锁；并发或过期请求不会重复修改错题记录。
    claimed = db.execute(update(Round).where(Round.id == session_id, Round.version == version)
                         .values(version=version + 1).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        raise ClassroomError("进度已更新，请继续当前题目", 409)
    db.refresh(session)
    question = db.query(Question).filter_by(session_id=session_id, position=session.cursor).first()
    if not question or question.id != question_id:
        db.rollback()
        raise ClassroomError("当前题目已变化，请刷新进度", 409)
    entry = db.get(Entry, question.entry_id)
    if not entry and question.stage != "done":
        db.rollback()
        return session_payload(db, session, library=library)
    snapshot = json.loads(question.snapshot)
    try:
        if action == "choice" and question.stage == "choice":
            if value not in json.loads(question.options):
                raise ClassroomError("请选择题目中的选项")
            question.picked = value
            question.stage = "spell"
            if value != snapshot["translation"]:
                mark_wrong(entry)
        elif action == "spell" and question.stage == "spell":
            if not value.strip():
                raise ClassroomError("请输入英文拼写")
            if normalize(value) != normalize(snapshot["english"]):
                question.spell_wrong = True
                mark_wrong(entry)
            else:
                question.rating = ("again" if question.picked != snapshot["translation"] else
                                   "hard" if question.spell_wrong else "good")
                question.stage = "done"
                if question.rating == "good" and entry.in_mistake_book:
                    entry.mistake_consec += 1
                    if entry.mistake_consec >= MISTAKE_EXIT_STREAK:
                        entry.in_mistake_book = False
                        entry.mistake_consec = 0
                elif question.rating != "good":
                    mark_wrong(entry)
                entry.completed += 1
        elif action == "next" and question.stage == "done":
            session.cursor += 1
        else:
            raise ClassroomError("当前答题阶段已变化，请刷新进度", 409)
        receipts.append(request_id)
        session.receipts = json.dumps(receipts)
        session.updated_at = datetime.now()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return session_payload(db, session, library=library)
