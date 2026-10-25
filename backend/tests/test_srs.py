"""SRS 算法与批改结果校验的单元测试。"""
import sys
import os
from datetime import date, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import srs


def make_card(**kw):
    base = dict(ease=2.5, interval_days=0, reps=0, lapses=0, status="new")
    base.update(kw)
    return SimpleNamespace(**base)


def test_new_card_good_goes_learning():
    card = make_card()
    today = date.today()
    interval = srs.review(card, srs.GOOD, today)
    assert card.status == "learning"
    assert interval == 1
    assert card.due == today + timedelta(days=1)


def test_graduation_to_review():
    card = make_card(status="learning", interval_days=1, reps=1)
    today = date.today()
    interval = srs.review(card, srs.GOOD, today)
    assert interval == 3
    assert card.status == "review"
    interval = srs.review(card, srs.GOOD, today)
    assert interval == 3 * card.ease


def test_again_resets_interval():
    card = make_card(status="review", interval_days=15, reps=5, ease=2.5)
    today = date.today()
    srs.review(card, srs.AGAIN, today)
    assert card.interval_days == 0
    assert card.status == "learning"
    assert card.lapses == 1
    assert card.ease == 2.3


def test_hard_increases_slowly():
    card = make_card(status="review", interval_days=10, reps=3)
    interval = srs.review(card, srs.HARD, date.today())
    assert interval == 12
    assert card.ease == 2.45


def test_mastered_threshold():
    card = make_card(status="review", interval_days=30)
    assert srs.is_mastered(card)
    card2 = make_card(status="review", interval_days=10)
    assert not srs.is_mastered(card2)
