"""单词/短语共用学习逻辑：学习队列、答题更新、浏览、测验生成。"""
import random
import time
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Phrase, ReviewLog, SrsCard, UserSetting, Word
from . import srs
from .phonetics import american_ipa
from .parts_of_speech import parts_of_speech

# 干扰项词池缓存：题库只读，短 TTL 缓存避免每次队列都全表扫描释义
_pool_cache: dict[tuple, tuple[float, list[str]]] = {}
_POOL_TTL = 300


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(UserSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str):
    row = db.get(UserSetting, key)
    if row:
        row.value = value
    else:
        db.add(UserSetting(key=key, value=value))


# ---------- 队列 ----------

def _translation_pool(db: Session, item_type: str, book: str) -> list[str]:
    key = (item_type, book)
    now = time.time()
    hit = _pool_cache.get(key)
    if hit and now - hit[0] < _POOL_TTL:
        return hit[1]
    if item_type == "word":
        rows = db.query(Word.translation).filter(Word.book == book).all()
    else:
        rows = db.query(Phrase.translation).filter(Phrase.book == book).all()
    pool, seen = [], set()
    for (t,) in rows:
        t = first_line(t, 40)
        if t and t not in seen:
            seen.add(t)
            pool.append(t)
    _pool_cache[key] = (now, pool)
    return pool


def first_line(t: str, limit: int) -> str:
    t = (t or "").replace("\\n", "\n")
    return t.split("\n")[0][:limit]


def _with_options(db: Session, item_type: str, book: str, payloads: list[dict]) -> list[dict]:
    """为卡片附加 4 选 1 选项（正确项 + 同词书干扰项，打乱）。"""
    if not payloads:
        return payloads
    pool = _translation_pool(db, item_type, book)
    for p in payloads:
        correct = first_line(p["translation"], 40)
        distractors = []
        seen = {correct}
        candidates = [t for t in pool if t not in seen]
        random.shuffle(candidates)
        for t in candidates:
            if t not in seen:
                seen.add(t)
                distractors.append(t)
            if len(distractors) == 3:
                break
        options = distractors + [correct]
        random.shuffle(options)
        p["options"] = options
        p["answer"] = correct
    return payloads


def study_queue(db: Session, item_type: str, book: str, source: str = "normal") -> dict:
    today = date.today()
    if source == "mistake":
        # 错题专项：仅错题卡，不受到期与配额限制
        cards = (db.query(SrsCard)
                 .filter(SrsCard.item_type == item_type, SrsCard.book == book,
                         SrsCard.in_mistake_book == True)  # noqa: E712
                 .order_by(SrsCard.due, SrsCard.id)
                 .all())
        payloads = _with_options(db, item_type, book, [_card_payload(db, c) for c in cards])
        return {"review": payloads, "new": [],
                "counts": {"review": len(payloads), "new": 0, "quota_left": 0,
                           "added_today": 0, "source": "mistake"}}

    # 到期复习卡
    review_cards = (
        db.query(SrsCard)
        .filter(SrsCard.item_type == item_type, SrsCard.book == book,
                SrsCard.status != "new", SrsCard.due <= today)
        .order_by(SrsCard.due)
        .all()
    )
    # 今日新学配额
    quota_key = "daily_new_phrases" if item_type == "phrase" else "daily_new_words"
    quota = int(get_setting(db, quota_key, "20") or 20)
    added_today = (
        db.query(func.count(SrsCard.id))
        .filter(SrsCard.item_type == item_type, SrsCard.book == book,
                SrsCard.added_at == today)
        .scalar() or 0
    )
    remain = max(0, quota - added_today)

    # 今日已建卡但仍为 new 的（上次队列没学完）直接回到队列，不占新配额
    pending_new = (
        db.query(SrsCard)
        .filter(SrsCard.item_type == item_type, SrsCard.book == book,
                SrsCard.status == "new", SrsCard.added_at == today)
        .order_by(SrsCard.id)
        .all()
    )

    new_items, new_cards = [], list(pending_new)
    remain -= len(pending_new)
    if remain > 0:
        # 找出尚无卡片的词条，按词频降序（常用优先）
        if item_type == "word":
            existing = {c.item_id for c in db.query(SrsCard).filter(
                SrsCard.item_type == "word", SrsCard.book == book).all()}
            pool = (db.query(Word)
                    .filter(Word.book == book, ~Word.id.in_(existing or {0}))
                    .order_by(Word.freq.desc(), Word.headword)
                    .limit(remain).all())
        else:
            existing = {c.item_id for c in db.query(SrsCard).filter(
                SrsCard.item_type == "phrase", SrsCard.book == book).all()}
            pool = (db.query(Phrase)
                    .filter(Phrase.book == book, ~Phrase.id.in_(existing or {0}))
                    .order_by(Phrase.id).limit(remain).all())
        for item in pool:
            card = SrsCard(item_type=item_type, item_id=item.id, book=book,
                           status="new", due=today, added_at=today)
            db.add(card)
            db.flush()
            new_cards.append(card)
            new_items.append(item)
        db.commit()

    review_payload = _with_options(db, item_type, book, [_card_payload(db, c) for c in review_cards])
    new_payload = _with_options(db, item_type, book, [_card_payload(db, c) for c in new_cards])
    return {
        "review": review_payload,
        "new": new_payload,
        "counts": {
            "review": len(review_payload),
            "new": len(new_payload),
            "quota_left": max(0, remain),
            "added_today": added_today,
            "source": "normal",
        },
    }


def _card_payload(db: Session, card: SrsCard) -> dict:
    base = {
        "card_id": card.id, "status": card.status, "due": str(card.due),
        "interval": card.interval_days, "reps": card.reps, "starred": card.starred,
        "in_mistake_book": bool(card.in_mistake_book), "mistake_consec": card.mistake_consec or 0,
    }
    if card.item_type == "word":
        w = db.get(Word, card.item_id)
        if w is None:
            return base
        base.update({
            "id": w.id, "headword": w.headword,
            "part_of_speech": parts_of_speech(w.headword, w.translation, w.definition),
            "phonetic_us": american_ipa(w.headword) or (w.phonetic_us if w.book == "custom" else ""),
            "translation": (w.translation or "").replace("\\n", "\n"),
            "definition": (w.definition or "").replace("\\n", "\n"),
            "book": w.book,
        })
    else:
        p = db.get(Phrase, card.item_id)
        if p is None:
            return base
        base.update({
            "id": p.id, "text": p.text,
            "translation": (p.translation or "").replace("\\n", "\n"),
            "note": (p.note or "").replace("\\n", "\n"), "book": p.book,
        })
    return base


# ---------- 答题 ----------

MISTAKE_EXIT_STREAK = 3  # 错题本连对次数达到该值自动移出


def answer(db: Session, card_id: int, rating: str) -> dict:
    card = db.get(SrsCard, card_id)
    if card is None:
        raise ValueError("卡片不存在")
    if rating not in (srs.AGAIN, srs.HARD, srs.GOOD):
        raise ValueError("无效评分")
    today = date.today()
    last_interval = card.interval_days
    next_interval = srs.review(card, rating, today)
    # 错题本维护：答错（again=选择错 / hard=拼写首试错）进入并清零连对；
    # 完全答对（good）连对 +1，达到阈值自动移出
    if rating == srs.GOOD:
        if card.in_mistake_book:
            card.mistake_consec = (card.mistake_consec or 0) + 1
            if card.mistake_consec >= MISTAKE_EXIT_STREAK:
                card.in_mistake_book = False
                card.mistake_consec = 0
    else:
        card.in_mistake_book = True
        card.mistake_consec = 0
    card.last_review_at = datetime.now()
    db.add(ReviewLog(card_id=card.id, item_type=card.item_type, rating=rating,
                     last_interval=last_interval, next_interval=next_interval))
    db.commit()
    return _card_payload(db, card)


# ---------- 错题本 ----------

def mistake_list(db: Session, item_type: str, book: str) -> list[dict]:
    cards = (db.query(SrsCard)
             .filter(SrsCard.item_type == item_type, SrsCard.book == book,
                     SrsCard.in_mistake_book == True)  # noqa: E712
             .order_by(SrsCard.due, SrsCard.id)
             .all())
    return [_card_payload(db, c) for c in cards]


# ---------- 进度 ----------

def book_progress(db: Session, item_type: str) -> list[dict]:
    """各词书进度：total(已建卡)/learned/mastered/starred + 词条总数。"""
    today = date.today()
    if item_type == "word":
        books = [r[0] for r in db.query(Word.book).distinct().all()]
        totals = dict(db.query(Word.book, func.count(Word.id)).group_by(Word.book).all())
    else:
        books = [r[0] for r in db.query(Phrase.book).distinct().all()]
        totals = dict(db.query(Phrase.book, func.count(Phrase.id)).group_by(Phrase.book).all())
    out = []
    for b in books:
        rows = (db.query(SrsCard.status, func.count(SrsCard.id))
                .filter(SrsCard.item_type == item_type, SrsCard.book == b)
                .group_by(SrsCard.status).all())
        counts = {s: n for s, n in rows}
        cards = (db.query(SrsCard)
                 .filter(SrsCard.item_type == item_type, SrsCard.book == b).all())
        mastered = sum(1 for c in cards if srs.is_mastered(c))
        starred = sum(1 for c in cards if c.starred)
        due_now = sum(1 for c in cards if c.status != "new" and c.due <= today)
        started = sum(n for s, n in rows if s != "new")
        out.append({
            "book": b, "total_items": totals.get(b, 0),
            "cards": sum(counts.values()), "new": counts.get("new", 0),
            "learning": counts.get("learning", 0), "review": counts.get("review", 0),
            "started": started, "mastered": mastered, "starred": starred,
            "due_now": due_now,
        })
    return out


# ---------- 浏览 ----------

def browse(db: Session, item_type: str, book: str, search: str = "",
           status: str = "all", starred: bool | None = None,
           page: int = 1, page_size: int = 30) -> dict:
    q = db.query(SrsCard).filter(SrsCard.item_type == item_type, SrsCard.book == book)
    if status == "new":
        q = q.filter(SrsCard.status == "new")
    elif status == "learning":
        q = q.filter(SrsCard.status == "learning")
    elif status == "review":
        q = q.filter(SrsCard.status == "review")
    elif status == "mastered":
        q = q.filter(SrsCard.status == "review", SrsCard.interval_days >= srs.MASTER_INTERVAL)
    if starred is not None:
        q = q.filter(SrsCard.starred == starred)
    items = []
    total = q.count()
    rows = (q.order_by(SrsCard.id.desc())
             .offset((page - 1) * page_size).limit(page_size).all())
    payloads = [_card_payload(db, c) for c in rows]
    if search:
        s = search.lower()
        payloads = [p for p in payloads if s in str(p.get("headword", "")).lower()
                    or s in str(p.get("text", "")).lower()
                    or s in str(p.get("translation", ""))]
        total = len(payloads)
    return {"total": total, "page": page, "items": payloads}


# ---------- 测验 ----------

def make_quiz(db: Session, item_type: str, book: str, count: int = 10,
              direction: str = "e2c") -> list[dict]:
    """从已开始学习的卡中出题；不足则补充新词。direction: e2c 英译中 / c2e 中译英。"""
    cards = (db.query(SrsCard)
             .filter(SrsCard.item_type == item_type, SrsCard.book == book,
                     SrsCard.status != "new")
             .order_by(func.random()).limit(count).all())
    if len(cards) < count:
        extra = (db.query(SrsCard)
                 .filter(SrsCard.item_type == item_type, SrsCard.book == book,
                         SrsCard.status == "new")
                 .order_by(func.random()).limit(count - len(cards)).all())
        cards += extra
    if not cards:
        return []
    payloads = [_card_payload(db, c) for c in cards]
    # 干扰项
    pool = _translation_pool(db, item_type, book)
    quiz = []
    for p in payloads:
        correct = first_line(p["translation"], 40)
        distractors = [d for d in random.sample(pool, min(12, len(pool))) if d != correct]
        seen, opts = set(), []
        for d in distractors:
            if d not in seen and d != correct:
                seen.add(d)
                opts.append(d)
            if len(opts) == 3:
                break
        options = opts + [correct]
        random.shuffle(options)
        quiz.append({
            "card_id": p["card_id"],
            "front": p.get("headword") or p.get("text"),
            "phonetic": p.get("phonetic_us", ""),
            "part_of_speech": p.get("part_of_speech", ""),
            "answer": correct,
            "options": options,
            "full_translation": p["translation"],
            "direction": direction,
        })
    return quiz
