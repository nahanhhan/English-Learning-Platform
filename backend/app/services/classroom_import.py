"""中英词表提取：只生成预览，不在解析阶段写数据库。"""
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .classroom import ClassroomError

_ocr = None
CHINESE = r"[\u3400-\u9fff]"


def parse_text(text, source="批量粘贴"):
    rows = []
    for line in text.replace("\r", "").split("\n"):
        raw = line.strip()
        if not raw or re.fullmatch(r"\d+", raw):
            continue
        clean = re.sub(r"^\s*\d+[.、)）]\s*", "", raw)
        # 制表符、竖线或中英交界。短语内部空格不得当作字段分隔。
        parts = re.split(r"\t+|\s*\|\s*", clean, maxsplit=1)
        if len(parts) == 2:
            english, translation = parts
        else:
            match = re.search(CHINESE, clean)
            if match:
                english, translation = clean[:match.start()], clean[match.start():]
            elif rows and rows[-1]["english"] and not rows[-1]["translation"] and not re.search(r"[A-Za-z]", clean):
                rows[-1]["translation"] = clean
                continue
            else:
                english, translation = (clean, "") if re.search(r"[A-Za-z]", clean) else ("", clean)
        english = re.sub(r"\s*[:：=—–]+\s*$", "", english).strip()
        # 只去除可明确识别的音标与词性，不猜测未配对的英文释义。
        english = re.sub(r"\s*/[^/]+/.*$", "", english).strip()
        english = re.sub(r"\s+(?:n|v|vt|vi|adj|adv|a|ad|prep|conj)\.\s*$", "", english).strip()
        translation = translation.strip()
        if english.lower() in ("英文", "english", "word", "单词") and translation in ("中文", "释义", "中文释义", "meaning"):
            continue
        rows.append({"english": english, "translation": translation,
                     "item_type": "phrase" if " " in english else "word", "source": source,
                     "raw": raw})
    return rows


def ocr_image(image):
    global _ocr
    try:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        result, _ = _ocr(image)
        # OCR 常把同一行的英文、中文识别为不同框，按行对齐后再配对。
        lines = []
        for box, text, score in sorted(result or [], key=lambda item: min(p[1] for p in item[0])):
            top, bottom = min(p[1] for p in box), max(p[1] for p in box)
            center, height = (top + bottom) / 2, max(1, bottom - top)
            line = next((line for line in reversed(lines)
                         if abs(line["center"] - center) <= min(line["height"], height) * 0.55), None)
            if line is None:
                line = {"center": center, "height": height, "parts": []}
                lines.append(line)
            line["parts"].append((min(p[0] for p in box), text))
        return "\n".join("\t".join(text for _, text in sorted(line["parts"])) for line in lines)
    except ImportError as exc:
        raise ClassroomError("扫描识别组件尚未安装，请重新运行 setup.bat 安装依赖") from exc


def extract_file(content: bytes, filename: str):
    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        raise ClassroomError("旧版 Word .doc 请先另存为 .docx 后导入")
    if suffix not in (".pdf", ".docx"):
        raise ClassroomError("请选择 PDF 或 Word .docx 文件")
    if not content:
        raise ClassroomError("文件为空")
    rows, originals = [], []
    try:
        if suffix == ".pdf":
            import pymupdf
            import numpy as np
            with pymupdf.open(stream=content, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise ClassroomError("PDF 已加密，请先解密后导入")
                for number, page in enumerate(doc, 1):
                    text = page.get_text(sort=True).strip()
                    bilingual = re.search(r"[A-Za-z]", text) and re.search(CHINESE, text)
                    if len(re.sub(r"\s", "", text)) < 8 or "\ufffd" in text or (page.get_images() and not bilingual):
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                        text = ocr_image(image)
                    source = f"{filename} · 第{number}页"
                    originals.append(f"{source}\n{text}")
                    rows.extend(parse_text(text, source))
        else:
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            with zipfile.ZipFile(io.BytesIO(content)) as doc:
                root = ET.fromstring(doc.read("word/document.xml"))
                body = root.find("w:body", ns)
                lines = []
                for block in body if body is not None else []:
                    if block.tag.endswith("}tbl"):
                        for row in block.findall("w:tr", ns):
                            cells = [" ".join("".join(node.text or "" for node in p.findall(".//w:t", ns))
                                              for p in cell.findall("w:p", ns))
                                     for cell in row.findall("w:tc", ns)]
                            lines.append("\t".join(cells))
                    else:
                        lines.append("".join(node.text or "" for node in block.findall(".//w:t", ns)))
            text = "\n".join(lines)
            originals.append(text)
            rows = parse_text(text, filename)
    except ClassroomError:
        raise
    except Exception as exc:
        raise ClassroomError("文件无法解析，请确认文件完整且格式正确；也可以复制词汇后批量粘贴") from exc
    if not rows:
        raise ClassroomError("未识别出文本，请检查文件；纯图片 Word 可另存为 PDF 后导入")
    return {"rows": rows, "raw_text": "\n\n".join(originals)}
