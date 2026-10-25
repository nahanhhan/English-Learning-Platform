import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import Base
from app.models import Grading, Question, Submission
from scripts.extract_questions import clean_chinese, clean_transcript, norm
from scripts.question_review import (
    IDENTITY, apply_review_to_extracted, load_review, render_reviewed_charts,
    sync_reviewed_questions,
)

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = json.loads((ROOT / "backend/data/questions.json").read_text(encoding="utf-8"))
REVIEW = load_review()


def find(exam, year, month, number, kind):
    return next(q for q in QUESTIONS if tuple(q[key] for key in IDENTITY) == (exam, year, month, number, kind))


def test_entire_question_bank_identity_and_clean_boundaries():
    assert len(QUESTIONS) == len({tuple(q[k] for k in IDENTITY) for q in QUESTIONS}) == 97
    assert Counter((q["exam_type"], q["q_type"]) for q in QUESTIONS) == {
        ("cet6", "writing"): 38, ("cet6", "translation"): 38,
        ("ky2", "translation"): 7, ("ky2", "small_writing"): 7, ("ky2", "big_writing"): 7,
    }
    for q in QUESTIONS:
        text = q["source_text"] or q["prompt"]
        assert q["ok"] and text.strip() and (ROOT / q["source_file"]).is_file()
        assert not re.search(r"第\s*\d+(?:[／/]\d+)?\s*页|[\x00-\x08\x0b\x0c\x0e-\x1f]|Listening Comprehension|Reading Comprehension|http[s]?://", text)
        if q["exam_type"] == "cet6" and q["q_type"] == "writing":
            assert text.count("Directions:") == 1
            assert len(text.split()) < 125
        if q["exam_type"] == "ky2" and q["q_type"] != "translation":
            points = 10 if q["q_type"] == "small_writing" else 15
            assert text.count(f"({points} points)") == 1
            assert text.endswith(f"({points} points)")
            assert "\n1) " in text and "\n2) " in text


def test_missing_first_sentence_and_mismatched_appendix_regressions():
    peony = find("cet6", 2019, 12, 1, "translation")["source_text"]
    assert peony.startswith("牡丹(peony)花色艳丽")
    assert "花中之王”。中国许多地方" in peony
    assert "中国国" not in peony
    red_chamber = find("cet6", 2020, 9, 2, "translation")["source_text"]
    assert "Dream of the Red Chamber" in red_chamber and "水浒传" not in red_chamber
    writing = find("cet6", 2020, 9, 2, "writing")["prompt"]
    assert "What is worth doing" in writing and "Wealth of the mind" not in writing
    assert find("cet6", 2021, 6, 2, "translation")["source_text"].startswith("青海是")
    assert "旅游目的地之一" in find("cet6", 2021, 6, 3, "translation")["source_text"]


@pytest.mark.parametrize("year,count", [(2020,3),(2021,2),(2022,2),(2023,3),(2024,2),(2025,4),(2026,4)])
def test_english_translation_preserves_source_paragraphs_and_no_page_numbers(year, count):
    text = find("ky2", year, 12, 1, "translation")["source_text"]
    assert len(text.split("\n\n")) == count
    assert not re.search(r"\s\d{1,2}$", text)
    assert len(text.split()) >= 130


def test_review_after_values_and_source_provenance():
    digests = {}
    for correction in REVIEW["corrections"]:
        current = next(q for q in QUESTIONS if all(q[k] == correction[k] for k in IDENTITY))
        assert correction["source_pages"]
        source = correction["source_file"]
        if source not in digests:
            digests[source] = hashlib.sha256((ROOT/source).read_bytes()).hexdigest()
        assert digests[source] == correction["source_sha256"]
        for field, values in correction["fields"].items():
            assert current[field] == values["after"]
            assert values["before"] != values["after"]


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def old_question(correction, identity=41):
    return Question(id=identity, **{k:correction[k] for k in IDENTITY},
                    title="原题", source_file=correction["source_file"],
                    **{field:values["before"] for field,values in correction["fields"].items()})


def test_incremental_sync_preserves_ids_submissions_grades_and_is_idempotent(db):
    correction = REVIEW["corrections"][0]
    question = old_question(correction)
    db.add(question); db.flush()
    submission = Submission(question_id=question.id, exam_type="cet6", q_type="translation",
                            title="旧练习", prompt="提交时题面", source_text=question.source_text,
                            content="original answer", status="done")
    db.add(submission); db.flush()
    grade = Grading(submission_id=submission.id, score=12, full_score=15, result_json='{"saved":true}')
    db.add(grade); db.commit()
    snapshot = submission.source_text
    assert sync_reviewed_questions(db, {"corrections":[correction]}) == 1
    db.commit()
    assert question.id == 41 and submission.question_id == 41
    assert submission.source_text == snapshot and grade.result_json == '{"saved":true}' and grade.score == 12
    assert db.query(Question).count() == db.query(Submission).count() == db.query(Grading).count() == 1
    assert sync_reviewed_questions(db, {"corrections":[correction]}) == 0


def test_sync_preserves_later_edits_and_unrelated_sources(db):
    correction = REVIEW["corrections"][0]
    question = old_question(correction)
    question.source_text = "用户另行修订的题目"
    db.add(question); db.commit()
    assert sync_reviewed_questions(db, {"corrections":[correction]}) == 0
    assert question.source_text == "用户另行修订的题目"
    question.source_text = correction["fields"]["source_text"]["before"]
    question.source_file = "other.pdf"
    db.commit()
    assert sync_reviewed_questions(db, {"corrections":[correction]}) == 0


def test_sync_skips_ambiguous_identity_and_does_not_commit(db):
    correction = REVIEW["corrections"][0]
    first, second = old_question(correction), old_question(correction,42)
    db.add_all([first,second]); db.commit()
    assert sync_reviewed_questions(db,{"corrections":[correction]}) == 0
    db.delete(second); db.commit()
    assert sync_reviewed_questions(db,{"corrections":[correction]}) == 1
    db.rollback()
    assert first.source_text == correction["fields"]["source_text"]["before"]


def test_extraction_reuses_verified_content_and_refuses_changed_pdf(tmp_path):
    correction = REVIEW["corrections"][0]
    extracted = {k:correction[k] for k in (*IDENTITY,"source_file")}
    extracted["source_text"] = "another OCR result"
    apply_review_to_extracted([extracted],ROOT)
    assert extracted["source_text"] == correction["fields"]["source_text"]["after"]
    fake = tmp_path / correction["source_file"].replace("\\","/")
    fake.parent.mkdir(parents=True); fake.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="原卷已变化"):
        apply_review_to_extracted([extracted],tmp_path)


def test_cleaning_preserves_english_word_spaces_and_removes_footer_and_following_section():
    assert clean_chinese("梅花 (plum blossom) 是 名花") == "梅花(plum blossom)是名花"
    assert clean_transcript("正文。第 12／12页 Part I Writing more") == "正文。"
    assert clean_transcript("《三国演义》(The Romance of the Three Kingdoms)正文。未得到监考教师指令前余文") == "《三国演义》(The Romance of the Three Kingdoms)正文。"
    assert norm("first\n12\fsecond\n13") == "first\nsecond"


def test_reviewed_chart_crops_include_titles_and_exclude_writing_instruction(tmp_path):
    render_reviewed_charts(ROOT,tmp_path)
    for chart in REVIEW["charts"]:
        with pymupdf.open(ROOT/chart["source_file"]) as doc:
            page=doc[chart["page"]-1]
            clip=pymupdf.Rect(chart["rect"])
            text=page.get_text(clip=clip)
            assert not re.search(r"ANSWER SHEET|\(15\s*points",text)
            if "cet6_2021_6_1" in chart["chart_image"]: assert "urbanization" in text
            if "cet6_2021_6_2" in chart["chart_image"]: assert "higher education" in text
            if "cet6_2021_6_3" in chart["chart_image"]: assert "Rural population" in text
            if "ky2_2026" in chart["chart_image"]: assert "儿童户外活动" in text
            assert (tmp_path/chart["chart_image"]).stat().st_size > 10000
