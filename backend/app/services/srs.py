"""SM-2 简化版间隔重复算法。

评分三档：again（不认识）/ hard（模糊）/ good（认识）
状态：new → learning → review
"""

AGAIN, HARD, GOOD = "again", "hard", "good"

# 掌握阈值：连续 interval ≥ 30 天视为已掌握
MASTER_INTERVAL = 30
LEARNING_STEPS = [0, 1, 3]  # 新卡学习步骤（天）


def review(card, rating: str, today) -> float:
    """根据评分更新卡片，返回下一次间隔（天）。card 需有 ease/interval_days/reps/lapses/status。"""
    ease = card.ease or 2.5
    interval = card.interval_days or 0

    if rating == AGAIN:
        ease = max(1.3, ease - 0.2)
        card.lapses = (card.lapses or 0) + 1
        interval = 0
        card.status = "learning"
        due = today  # 今天内重新排队
    elif rating == HARD:
        ease = max(1.3, ease - 0.05)
        if card.status == "new" or interval == 0:
            interval = 0.5  # 半天后
        else:
            interval = max(1, interval * 1.2)
        card.status = "learning" if interval < 1 else "review"
        due = _add_days(today, interval)
    else:  # good
        if card.status == "new" or interval == 0:
            interval = LEARNING_STEPS[1]
            card.status = "learning"
        elif interval < LEARNING_STEPS[2]:
            interval = LEARNING_STEPS[2]
            card.status = "review"
        else:
            interval = interval * ease
            card.status = "review"
        due = _add_days(today, interval)

    card.ease = ease
    card.interval_days = interval
    card.reps = (card.reps or 0) + 1
    card.due = due
    return interval


def _add_days(today, days: float):
    from datetime import timedelta
    minutes = days < 1
    if minutes:
        return today  # 半天内仍视为今天到期，前端可在本轮尾部重刷
    return today + timedelta(days=int(round(days)))


def is_mastered(card) -> bool:
    return card.interval_days >= MASTER_INTERVAL and card.status == "review"
