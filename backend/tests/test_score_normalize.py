"""百分制分数折算的测试。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import grading


def _grade_with_score(score_value, full=15):
    """绕过真实 AI 调用，只测 grade 内的分数归一化逻辑。"""
    import app.services.ai_client as ai_client_mod
    from app.services import grading as g

    def fake_chat(provider, messages, **kw):
        import json as _json
        return _json.dumps({
            "score": score_value, "band": "10-12分档",
            "dimensions": {"accuracy": 3, "language": 3, "fluency": 3},
            "overall_comment": "ok", "errors": [], "good_points": [],
            "improved_version": "x", "key_notes": [],
        }, ensure_ascii=False)

    orig = ai_client_mod.chat
    ai_client_mod.chat = fake_chat
    try:
        return g.grade("cet6", "translation", "题", "原文", "译文", 5,
                       {"base_url": "https://x", "api_key": "k", "model": "m"}, full)
    finally:
        ai_client_mod.chat = orig


def test_score_percent_scaled():
    assert _grade_with_score(55)["score"] in (8.2, 8.3)  # 55/100 * 15（浮点边界）


def test_score_percent_small_full():
    assert _grade_with_score(70, full=10)["score"] == 7.0


def test_score_normal_passthrough():
    assert _grade_with_score(12.5)["score"] == 12.5


def test_score_absurd_clamped():
    assert _grade_with_score(300)["score"] == 15
