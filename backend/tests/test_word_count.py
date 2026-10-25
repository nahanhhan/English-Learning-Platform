"""字数区间解析与润色版字数保障的测试。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import grading
from app.services import ai_client


def test_parse_at_least_no_more():
    p = "You should write at least 150 words but no more than 200 words."
    assert grading.parse_word_range(p, "cet6", "writing") == (150, 200)


def test_parse_about_words():
    p = "You should write about 100 words on the ANSWER SHEET."
    wmin, wmax = grading.parse_word_range(p, "ky2", "small_writing")
    assert wmin == 100 and 125 <= wmax <= 135


def test_parse_defaults():
    assert grading.parse_word_range("", "cet6", "writing") == (150, 200)
    assert grading.parse_word_range("", "ky2", "big_writing") == (150, 180)
    assert grading.parse_word_range("", "ky2", "translation") is None


def test_ensure_word_count_skips_when_ok(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_client, "chat", lambda *a, **k: calls.append(a))
    result = {"polished_version": "word " * 160, "model_essay": "word " * 155}
    grading._ensure_word_count(result, "cet6", "writing",
                               "at least 150 words but no more than 200 words.", {})
    assert calls == []
    assert "word_warnings" not in result


def test_ensure_word_count_expands_short_essay(monkeypatch):
    def fake_chat(provider, messages, **kw):
        return "expanded " * 160
    monkeypatch.setattr(ai_client, "chat", fake_chat)
    result = {"polished_version": "short " * 50, "model_essay": "fine " * 160}
    grading._ensure_word_count(result, "cet6", "writing",
                               "at least 150 words but no more than 200 words.", {})
    assert count_ok(result["polished_version"])
    assert "word_warnings" not in result


def test_ensure_word_count_warning_when_repair_fails(monkeypatch):
    def fake_chat(provider, messages, **kw):
        return "still " * 30
    monkeypatch.setattr(ai_client, "chat", fake_chat)
    result = {"polished_version": "short " * 50, "model_essay": "fine " * 160}
    grading._ensure_word_count(result, "cet6", "writing",
                               "at least 150 words but no more than 200 words.", {})
    assert "word_warnings" in result


def count_ok(text):
    return 150 <= len(text.split()) <= 200


def test_count_words():
    assert grading.count_words("hello world  foo") == 3
    assert grading.count_words("") == 0
