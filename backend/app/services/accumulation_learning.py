"""积累词汇的真实作答统计及 60% / 20% / 20% 选题。"""
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction

from sqlalchemy import and_, case, func, select

from ..models import AccumulationReviewLog as Log


@dataclass(frozen=True)
class LearningStats:
    attempts: int = 0
    correct: int = 0
    recent_attempts: int = 0
    recent_correct: int = 0
    last_practiced_at: datetime | None = None

    @property
    def accuracy(self):
        if not self.attempts:
            return None
        return (Fraction(4, 5) * Fraction(self.recent_correct, self.recent_attempts)
                + Fraction(1, 5) * Fraction(self.correct, self.attempts))

    def payload(self):
        return {
            "recent_accuracy": self.recent_correct / self.recent_attempts if self.recent_attempts else None,
            "recent_attempts": self.recent_attempts,
            "last_practiced_at": self.last_practiced_at.isoformat() + "Z" if self.last_practiced_at else None,
        }


def statistics(db, entry_ids):
    """批量获取累计及最近十次统计，不把整份历史加载到内存。"""
    if not entry_ids:
        return {}
    correct = case((and_(Log.choice_correct, Log.spelling_correct), 1), else_=0)
    window = dict(partition_by=Log.entry_id)
    ranked = select(
        Log.entry_id, correct.label("correct"),
        func.count().over(**window).label("attempts"),
        func.sum(correct).over(**window).label("total_correct"),
        func.max(Log.completed_at).over(**window).label("latest"),
        func.row_number().over(**window, order_by=(Log.completed_at.desc(), Log.id.desc())).label("position"),
    ).where(Log.entry_id.in_(entry_ids)).subquery()
    rows = db.execute(select(ranked).where(ranked.c.position <= 10)).mappings()
    collected = {}
    for row in rows:
        value = collected.setdefault(row["entry_id"], {
            "attempts": row["attempts"], "correct": row["total_correct"],
            "last_practiced_at": row["latest"], "recent_attempts": 0, "recent_correct": 0,
        })
        value["recent_attempts"] += 1
        value["recent_correct"] += row["correct"]
    return {entry_id: LearningStats(**value) for entry_id, value in collected.items()}


def _ranks(values):
    """升序百分位平均秩：最低为 0，最高为 1，并列取平均。"""
    ordered = sorted(values, key=values.get)
    if len(ordered) < 2:
        return {key: Fraction(1, 2) for key in ordered}
    result, start = {}, 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = Fraction(start + end - 1, 2 * (len(ordered) - 1))
        for key in ordered[start:end]:
            result[key] = rank
        start = end
    return result


def priorities(entries, stats):
    """只在筛选后的候选内排名；未知不伪装成零正确率或旧日期。"""
    accuracy, elapsed, counts = {}, {}, {}
    epoch = datetime(1970, 1, 1)
    for entry in entries:
        value = stats.get(entry.id, LearningStats())
        if value.accuracy is not None:
            accuracy[entry.id] = -value.accuracy
        if value.last_practiced_at is not None:
            # 对同一时刻的候选，距今越久等价于完成时间越早，无需引入建议日期。
            elapsed[entry.id] = -(value.last_practiced_at - epoch).total_seconds()
        counts[entry.id] = -entry.completed
    accuracy, elapsed, counts = _ranks(accuracy), _ranks(elapsed), _ranks(counts)
    neutral = Fraction(1, 2)
    result = {}
    for entry in entries:
        weakness = accuracy.get(entry.id, Fraction(1) if entry.in_mistake_book else neutral)
        result[entry.id] = (Fraction(3, 5) * weakness
                            + Fraction(1, 5) * elapsed.get(entry.id, neutral)
                            + Fraction(1, 5) * counts[entry.id])
    return result


def select_entries(entries, stats):
    scores = priorities(entries, stats)
    return sorted(entries, key=lambda entry: (-scores[entry.id], entry.id))[:50]


def record_completion(db, session, question, translation):
    # 调用者已经在同一事务内取得轮次版本写锁；唯一题目编号再防止重复记次。
    db.add(Log(entry_id=question.entry_id, session_id=session.id, question_id=question.id,
               choice_correct=question.picked == translation,
               spelling_correct=not question.spell_wrong,
               completed_at=datetime.now(timezone.utc).replace(tzinfo=None)))
