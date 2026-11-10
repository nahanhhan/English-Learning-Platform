"""作文估分依据、可选建议和已有考试规则兼容。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import ai_client, grading, short_translation
from app.services.writing_policy import CET6_WRITING_VERSION, KY2_WRITING_VERSION


def response(**overrides):
    item = {'score': 11, 'band': '1-3分档', 'overall_comment': '思想清楚，有少量小错。',
            'score_reason': '切题且连贯，出现少量不影响理解的语言错误，符合10至12分档。',
            'dimensions': {'task': 4, 'structure': 4, 'language': 3},
            'errors': [{'fragment':'he go', 'issue_type':'语法', 'explanation':'主谓不一致', 'suggestion':'he goes'}],
            'optional_suggestions': [{'original':"I'm", 'suggestion':'I am', 'reason':'可选，不影响评分'}],
            'paragraph_comments': [], 'vocab_upgrades': [], 'structure_advice': '',
            'polished_version': 'word ' * 155, 'model_essay': 'word ' * 155}
    item.update(overrides)
    return item


def test_cet6_writing_records_actual_score_evidence_and_separates_suggestions(monkeypatch):
    received = []
    def chat(provider, messages, **kwargs):
        received.append(messages)
        return json.dumps(response(), ensure_ascii=False)
    monkeypatch.setattr(ai_client, 'chat', chat)
    result = grading.grade('cet6', 'writing', 'Write at least 150 words but no more than 200 words.', '', 'my essay', 150, {})
    assert result['score'] == 11 and result['band'] == '10-12分档'
    assert result['rubric_version'] == CET6_WRITING_VERSION and result['score_reason'] == response()['score_reason']
    assert result['errors'][0]['fragment'] == 'he go'
    assert result['optional_suggestions'][0]['original'] == "I'm"
    assert not any(item.get('fragment') == "I'm" for item in result['errors'])
    assert '允许个别小错' in received[0][1]['content']
    assert '其中有一些严重错误' in received[0][1]['content']
    assert '不得声称确定的官方分数' in received[0][0]['content']


@pytest.mark.parametrize('reason', [None, '', '  ', {'not':'text'}])
def test_new_writing_rejects_missing_overall_evidence(monkeypatch, reason):
    monkeypatch.setattr(ai_client, 'chat', lambda *a, **k: json.dumps(response(score_reason=reason)))
    with pytest.raises(ai_client.AiError, match='评分依据'):
        grading.grade('cet6', 'writing', 'Write about 150 words.', '', 'my essay', 2, {})


def test_kaoyan_writing_keeps_own_rubric_and_complete_feedback(monkeypatch):
    messages = grading.build_writing_prompt('ky2', 'small_writing', 'Write about 100 words.', '', 'Dear Sam,', 10, 2)
    assert '应用文各档为9-10' in messages[1]['content']
    monkeypatch.setattr(ai_client, 'chat', lambda *a, **k: json.dumps(response(score=7, polished_version='word '*110, model_essay='word '*110)))
    result = grading.grade('ky2', 'small_writing', 'Write about 100 words.', '', 'Dear Sam,', 2, {}, 10)
    assert result['score'] == 7 and result['band'] == '7-8分档' and result['rubric_version'] == KY2_WRITING_VERSION
    assert result['score_reason'] and result['optional_suggestions']


def test_old_writing_results_still_validate_without_new_fields():
    old = grading._validate({'score': 11, 'overall_comment': '旧结果'}, 'writing')
    assert old['score'] == 11 and old['optional_suggestions'] == []


def test_both_translation_paths_check_ambiguity_in_context():
    data = {'sentences':['请你决定。'], 'reference':'It is up to you.', 'key_points':['决定'], 'training_points':['表达决定']}
    messages = short_translation.build_messages(data, 'It is up to you.')
    paragraph = grading.build_translation_prompt('cet6', '请你决定。', '翻译', 'It is up to you.')
    for result in (messages, paragraph):
        assert '词语在其他语境还有其他意思，不等于本句有歧义' in result[0]['content']
        assert '两种读法在本句为何均合理' in result[0]['content']


@pytest.mark.parametrize('score', [-1, 11, 70, None, float('nan'), True])
def test_writing_rejects_invalid_score_instead_of_guessing_or_clamping(monkeypatch, score):
    monkeypatch.setattr(ai_client, 'chat', lambda *a, **k: json.dumps(response(score=score)))
    with pytest.raises(ai_client.AiError, match='满分制'):
        grading.grade('ky2', 'small_writing', 'Write about 100 words.', '', 'answer', 1, {}, 10)


@pytest.mark.parametrize('score,expected', [(10,'9-10分档'), (9,'9-10分档'), (8,'7-8分档'), (6,'5-6分档'), (4,'3-4分档'), (2,'1-2分档'), (0,'0分')])
def test_kaoyan_application_bands(score, expected):
    assert grading.writing_band(score, 'ky2', 'small_writing') == expected


def test_fractional_score_between_bands_is_not_labelled_as_inside_either():
    assert grading.writing_band(8.5, 'ky2', 'small_writing') == '7-8分档与9-10分档之间'
    assert grading.writing_band(12.5, 'cet6', 'writing') == '10-12分档与13-15分档之间'
