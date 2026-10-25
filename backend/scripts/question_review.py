"""按逐题核对清单修正题库，保持既有题目 ID 与提交快照。"""
import hashlib
import json
import logging
from pathlib import Path

REVIEW_PATH = Path(__file__).resolve().parents[1] / "data/question_corrections.json"
IDENTITY = ("exam_type", "year", "month", "set_no", "q_type")
EDITABLE = {"prompt", "source_text", "chart_image", "notes"}


def load_review(path=REVIEW_PATH):
    review = json.loads(Path(path).read_text(encoding="utf-8"))
    for correction in review["corrections"]:
        if not set(correction["fields"]).issubset(EDITABLE):
            raise ValueError("题库更正不得修改身份字段")
    return review


def same_source(left, right):
    return left.replace("\\", "/") == right.replace("\\", "/")


def sync_reviewed_questions(db, review=None):
    """只替换仍等于核对前内容的字段，不覆盖后来手动修改的题目。由调用者提交事务。"""
    from app.models import Question

    changed = 0
    for correction in (review or load_review())["corrections"]:
        identity = {key: correction[key] for key in IDENTITY}
        rows = db.query(Question).filter_by(**identity).all()
        if len(rows) != 1 or not same_source(rows[0].source_file, correction["source_file"]):
            continue
        row = rows[0]
        updated = False
        for field, values in correction["fields"].items():
            current = getattr(row, field)
            if current == values["before"]:
                setattr(row, field, values["after"])
                updated = True
            elif current != values["after"]:
                logging.getLogger(__name__).warning("保留已修改的题目字段：%s %s", row.id, field)
        changed += int(updated)
    db.flush()
    return changed


def apply_review_to_extracted(questions, root, review=None):
    """重抽取时继续使用已逐页核实的更正；原卷变化时要求重新核对。"""
    review = review or load_review()
    checksums = {}
    corrections = {tuple(item[key] for key in IDENTITY): item for item in review["corrections"]}
    for question in questions:
        correction = corrections.get(tuple(question[key] for key in IDENTITY))
        if not correction or not same_source(question["source_file"], correction["source_file"]):
            continue
        source = correction["source_file"]
        if source not in checksums:
            path = Path(root) / source.replace("\\", "/")
            checksums[source] = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksums[source] != correction["source_sha256"]:
            raise ValueError(f"原卷已变化，请重新核对：{source}")
        for field, values in correction["fields"].items():
            question[field] = values["after"]
        question["ok"] = True


def render_reviewed_charts(root, output, review=None):
    import pymupdf

    for chart in (review or load_review()).get("charts", []):
        path = Path(root) / chart["source_file"].replace("\\", "/")
        if hashlib.sha256(path.read_bytes()).hexdigest() != chart["source_sha256"]:
            raise ValueError(f"图表原卷已变化，请重新核对：{chart['source_file']}")
        target = Path(output) / chart["chart_image"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(path) as doc:
            page = doc[chart["page"] - 1]
            page.get_pixmap(matrix=pymupdf.Matrix(2.4, 2.4), clip=pymupdf.Rect(chart["rect"]), alpha=False).save(target)
