"""批改 Prompt 构建与结果校验的测试。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import grading
from app.services.ai_client import extract_json


def test_full_scores():
    assert grading.FULL_SCORES[("cet6", "translation")] == 15
    assert grading.FULL_SCORES[("ky2", "small_writing")] == 10
    assert grading.FULL_SCORES[("ky2", "big_writing")] == 15


def test_build_translation_prompt_contains_rubric_and_source():
    msgs = grading.build_translation_prompt(
        "cet6", "牡丹是中国的名花。", "将段落翻译成英文", "Peony is a famous flower.", 15)
    assert msgs[0]["role"] == "system"
    assert "牡丹是中国的名花" in msgs[1]["content"]
    assert "Peony is a famous flower." in msgs[1]["content"]
    assert "13-15分档" in msgs[1]["content"]  # 六级评分标准
    msgs2 = grading.build_translation_prompt(
        "ky2", "Peony is a flower.", "Translate into Chinese", "牡丹是一种花。", 15)
    assert "第四档" in msgs2[1]["content"]  # 考研评分标准


def test_build_writing_prompt():
    msgs = grading.build_writing_prompt("ky2", "small_writing", "Write an email...", "", "Dear Jack,", 10, 100)
    assert "格式和语域" in msgs[1]["content"]
    assert "Dear Jack," in msgs[1]["content"]


def test_validate_fills_missing_fields():
    result = grading._validate({"score": "12"}, "translation")
    assert result["dimensions"]["accuracy"] == 0
    assert result["errors"] == []
    assert result["improved_version"] == ""
    r2 = grading._validate({"score": 8}, "writing")
    assert r2["dimensions"]["task"] == 0
    assert r2["model_essay"] == ""


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('好的，结果如下：{"a": 3} 以上') == {"a": 3}


def test_mock_grading_shape():
    m = grading.mock_grading("cet6", "translation", 15)
    assert m["score"] <= 15
    assert "dimensions" in m
    w = grading.mock_grading("ky2", "big_writing", 15)
    assert "model_essay" in w
