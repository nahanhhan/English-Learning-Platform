"""从真题 PDF 抽取六级翻译/作文题与考研英语二翻译/小作文/大作文题。

处理三类来源：
1. 文本型 PDF —— 直接抽取（大部分）。
2. 中文乱码卷（2019.12、2020.09、2020.12 第3套、2021.12 第3套）—— 翻译段用 OCR。
3. 考研 2020/2022/2023 最后一页为扫描图 —— 大作文题干与图表用 OCR + 裁图。

输出 data/questions.json；考研大作文图表存 data/charts/ky2_{year}.png。
"""
import json
import os
import re
import sys

import numpy as np
import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from scripts.question_review import apply_review_to_extracted, render_reviewed_charts
SIX_DIR = os.path.join(ROOT, "六级")
KY_DIR = os.path.join(ROOT, "考研英语二")
OUT_DIR = os.path.join(ROOT, "backend", "data")
CHART_DIR = os.path.join(OUT_DIR, "charts")
os.makedirs(CHART_DIR, exist_ok=True)

_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


# ---------------- 文本清洗 ----------------

def norm(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"zhenti\.burningvocabulary\.\S+", " ", text, flags=re.IGNORECASE)
    # 按页处理：剥掉页首页尾的孤立页码行
    pages = text.split("\f")
    cleaned_pages = []
    for pg in pages:
        lines = [ln.strip() for ln in pg.splitlines() if ln.strip()]
        # 去页脚 “第 12/12页”（半角/全角斜杠均可）
        lines = [ln for ln in lines
                 if not re.fullmatch(r"第\s*\d+\s*[／/]\s*\d+\s*页.{0,8}", ln)]
        if lines and re.fullmatch(r"\d{1,2}", lines[0]):
            lines = lines[1:]
        if lines and re.fullmatch(r"\d{1,2}", lines[-1]):
            lines = lines[:-1]
        cleaned_pages.append("\n".join(lines))
    return "\n".join(cleaned_pages)


def clean_english(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.:;!?'])", r"\1", s)
    return s.strip()


def clean_chinese(s: str) -> str:
    # 中文去排版空格，但保留英文提示词之间的空格。
    s = re.sub(r"(?<=[A-Za-z0-9])\s+(?=[A-Za-z0-9])", "\ue000", s)
    return re.sub(r"\s+", "", s).replace("\ue000", " ").strip()


JUNK_PATTERNS = [
    r"（?请于正式开考后半小时内完成该部分，之后将进行听力考试）?",
    r"附：第\d+套作文及翻译",
    r"^第\d+页?$",
    r"\(30\s*minutes\)",
    r"^（\d+）",
]


def clean_transcript(s: str) -> str:
    """清理 OCR/文本层翻译段落中的杂行。"""
    for pat in JUNK_PATTERNS:
        s = re.sub(pat, "", s)
    s = re.sub(r"第\s*\d+(?:\s*[／/]\s*\d+)?\s*页", "", s)
    s = re.split(r"未得到监考教师指令前|Part\s*I\b\s*Writing", s, maxsplit=1)[0]
    return clean_chinese(s).rstrip("()")


def cjk_count(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s))


# ---------------- OCR ----------------

def page_image(page, zoom=2.6) -> np.ndarray:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return img


def ocr_lines(page, zoom=2.6):
    """返回 [(y, x, text, score)]，按阅读顺序。"""
    img = page_image(page, zoom)
    result, _ = get_ocr()(img)
    if not result:
        return [], img
    items = []
    for box, text, score in result:
        y = min(p[1] for p in box)
        x = min(p[0] for p in box)
        items.append((y, x, text.strip(), float(score)))
    items.sort(key=lambda t: (t[0], t[1]))
    return items, img


def ocr_cet6_translation(pdf_path: str) -> str:
    """OCR 含 Part IV Translation 的页面，取中文段落。"""
    doc = pymupdf.open(pdf_path)
    target = None
    for i, pg in enumerate(doc):
        t = re.sub(r"\s+", " ", pg.get_text())
        if re.search(r"Part\s*IV", t) and re.search(r"Translation", t, re.IGNORECASE):
            target = i
            break  # 附录可能还有另一套翻译，不能取最后一个标记。
    # 部分乱码卷 Part IV 标记本身可读；再兜底取最后一页
    pages = [target] if target is not None else [len(doc) - 1]
    doc_pages = [doc[i] for i in pages]
    pieces = []
    for pg in doc_pages:
        items, _ = ocr_lines(pg)
        lines = [t for (y, x, t, s) in items if s > 0.55 and cjk_count(t) >= 2]
        pieces.extend(lines)
    doc.close()
    text = "".join(pieces)
    text = re.sub(r"\s+", "", text)
    return text


def ocr_ky2_last_page(pdf_path: str, year: int):
    """考研最后一页为扫描图：OCR 大作文题干 + 在题干下方裁剪图表（暗像素包围盒）。"""
    import cv2

    doc = pymupdf.open(pdf_path)
    pg = doc[len(doc) - 1]
    items, img = ocr_lines(pg, zoom=2.2)
    texts = [(y, t) for (y, x, t, s) in items if s > 0.5]
    doc.close()

    prompt, chart_path = "", ""
    idx_dir = next((i for i, (y, t) in enumerate(texts) if "Directions" in t), None)
    if idx_dir is not None:
        out = []
        for i in range(idx_dir, len(texts)):
            t = texts[i][1]
            out.append(t)
            if re.search(r"points?\s*\)", t):
                break
        prompt = clean_english(" ".join(out))

        h, w = img.shape[:2]
        y0 = int(texts[idx_dir + len(out) - 1][0]) + 44
        region = img[y0: int(h * 0.94), int(w * 0.03): int(w * 0.97)]
        gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        ys, xs = np.where(gray < 200)
        if len(ys) > 200:
            pad = 14
            cy0, cy1 = int(ys.min()), int(ys.max())
            cx0, cx1 = int(xs.min()), int(xs.max())
            crop = region[max(cy0 - pad, 0): cy1 + pad, max(cx0 - pad, 0): cx1 + pad]
            out_name = f"ky2_{year}.png"
            cv2.imwrite(os.path.join(CHART_DIR, out_name), crop)
            chart_path = f"charts/{out_name}"
    if not chart_path:
        # 兜底：整页保存
        import cv2
        out_name = f"ky2_{year}.png"
        cv2.imwrite(os.path.join(CHART_DIR, out_name), img)
        chart_path = f"charts/{out_name}"
    return prompt, chart_path


# ---------------- 六级 ----------------

def ocr_cet6_writing(pdf_path: str) -> str:
    """写作题不在文本层时（整段图片），逐页 OCR 定位 Directions 段。"""
    doc = pymupdf.open(pdf_path)
    prompt = ""
    for pg in doc:
        items, _ = ocr_lines(pg, zoom=2.2)
        texts = [t for (y, x, t, s) in items if s > 0.5]
        start = None
        for i, t in enumerate(texts):
            if re.search(r"Directions\s*:?\s*For this part.{0,30}write", t, re.IGNORECASE):
                start = i
                break
        if start is None:
            continue
        seg = [texts[start]]
        for t in texts[start + 1:]:
            if re.match(r"Part\s+[IV]", t) or re.search(r"[\u4e00-\u9fff]", t):
                break
            seg.append(t)
            if re.search(r"words\s*\.?\s*$", t):
                break
        prompt = clean_english(" ".join(seg))
        if len(prompt) >= 60:
            break
    doc.close()
    return prompt


def extract_cet6_chart(pdf_path: str, tag: str) -> str:
    """图表作文：取写作页最大的嵌入图片，否则矢量聚类。"""
    doc = pymupdf.open(pdf_path)
    page_idx = None
    for i, pg in enumerate(doc):
        t = re.sub(r"\s+", " ", pg.get_text())
        if re.search(r"Part\s*I\b.{0,80}Writing", t):
            page_idx = i
            break
    out_path, out_name = "", ""
    if page_idx is not None:
        pg = doc[page_idx]
        best, best_area = None, 0
        for im in pg.get_images(full=True):
            try:
                pix = pymupdf.Pixmap(doc, im[0])
                if pix.width * pix.height > best_area and pix.width > 150 and pix.height > 90:
                    best, best_area = pix, pix.width * pix.height
            except Exception:
                continue
        if best is not None:
            out_name = f"cet6_{tag}.png"
            if best.n - best.alpha > 3:
                best = pymupdf.Pixmap(pymupdf.csRGB, best)
            best.save(os.path.join(CHART_DIR, out_name))
            out_path = f"charts/{out_name}"
    doc.close()
    return out_path


def extract_cet6(pdf_path: str, tag: str = "") -> list[dict]:
    doc = pymupdf.open(pdf_path)
    raw = "\f".join(pg.get_text() for pg in doc)
    doc.close()
    text = norm(raw)
    flat = re.sub(r"\s+", " ", text)

    out = []

    # ---- 写作：Part I Writing (30 minutes) → Directions 文本 ----
    m = re.search(r"Part\s*I\b.{0,80}?Writing", flat)
    prompt = ""
    if m:
        seg = flat[m.start():]
        dm = re.search(r"Directions\s*:\s*", seg)
        if dm:
            body = seg[dm.end():]
            stop = re.search(r"Part\s*(II|IV)\b", body)
            if stop:
                body = body[: stop.start()]
            # 截到第一个中文字符（答题卡警示等）
            cm = re.search(r"[\u4e00-\u9fff]", body)
            if cm:
                body = body[: cm.start()]
            prompt = clean_english(body[:900])
    if not prompt:
        try:
            prompt = ocr_cet6_writing(pdf_path)
        except Exception as e:
            print(f"    writing OCR failed: {e}")
    chart = ""
    if prompt and re.search(r"chart|graph|table", prompt, re.IGNORECASE):
        try:
            chart = extract_cet6_chart(pdf_path, tag)
        except Exception as e:
            print(f"    chart extract failed: {e}")
    out.append({
        "q_type": "writing",
        "prompt": f"Directions: {prompt}" if prompt else "",
        "source_text": "",
        "chart_image": chart,
        "ok": len(prompt) >= 60 and cjk_count(prompt) == 0,
    })

    # ---- 翻译：Part IV Translation (30 minutes) → 中文段 ----
    m = re.search(r"Part\s*IV\s*Translation", flat)
    source = ""
    if m:
        seg = flat[m.end():]
        seg = re.sub(r"Directions\s*:.*?(Answer\s*Sheet\s*2\.?|$)", " ", seg,
                     count=1, flags=re.DOTALL | re.IGNORECASE)
        source = clean_chinese(seg)
    ok = cjk_count(source) >= 80
    if not ok:
        # 文本层缺失或乱码 → OCR
        try:
            source = ocr_cet6_translation(pdf_path)
            ok = cjk_count(source) >= 80
        except Exception as e:
            print(f"    OCR failed: {e}")
            source = source or ""
    source = clean_transcript(source)
    out.append({
        "q_type": "translation",
        "prompt": "将下面这段汉语文章翻译成英文。",
        "source_text": source,
        "ok": ok,
    })
    return out


# ---------------- 考研英语二 ----------------

def extract_ky2(pdf_path: str, year: int) -> list[dict]:
    doc = pymupdf.open(pdf_path)
    raw = "\f".join(pg.get_text() for pg in doc)
    text = norm(raw)
    text = re.sub(r"[ \u00a0]+", " ", text)
    res = []

    # 翻译：Section III → Section IV
    m = re.search(r"Section\s*III\s*Translation(.*?)Section\s*IV", text, re.DOTALL | re.IGNORECASE)
    if m:
        body = m.group(1)
        body = re.sub(r"^\s*\d+\s*\.\s*Directions\s*:.*?\(15\s*points\)\s*", "", body,
                      count=1, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"Section\s*IV.*$", "", body, flags=re.DOTALL)
        body = clean_english(body)
        body = re.sub(r"\(15\s*points?\)\s*$", "", body, flags=re.IGNORECASE)
        res.append({
            "q_type": "translation",
            "prompt": "Translate the following text into Chinese. Write your translation on the ANSWER SHEET. (15 points)",
            "source_text": body, "ok": len(body) >= 200,
        })
    else:
        res.append({"q_type": "translation", "prompt": "", "source_text": "", "ok": False})

    # 小作文 Part A / 大作文 Part B
    sec4 = re.search(r"Section\s*IV\s*Writing(.*?)$", text, re.DOTALL | re.IGNORECASE)
    part_a_prompt, part_b_prompt = "", ""
    if sec4:
        sec4_text = sec4.group(1)
        pa = re.search(r"Part\s*A(.*?)(?:Part\s*B|$)", sec4_text, re.DOTALL | re.IGNORECASE)
        pb = re.search(r"Part\s*B(.*?)$", sec4_text, re.DOTALL | re.IGNORECASE)
        if pa:
            part_a_prompt = clean_english(re.sub(r"^\s*\d+\s*\.\s*Directions\s*:\s*", "", pa.group(1).strip()))
            part_a_prompt = re.sub(r"\s*\(10\s*points?\)\s*$", "", part_a_prompt, flags=re.IGNORECASE)
        if pb:
            part_b_prompt = clean_english(re.sub(r"^\s*\d+\s*\.\s*Directions\s*:\s*", "", pb.group(1).strip()))
            cm = re.search(r"[一-鿿]", part_b_prompt)  # 截掉图表内嵌文字
            if cm:
                part_b_prompt = part_b_prompt[: cm.start()].strip()
    res.append({"q_type": "small_writing",
                "prompt": (part_a_prompt + " (10 points)") if part_a_prompt else "",
                "source_text": "", "ok": len(part_a_prompt) >= 60})
    res.append({"q_type": "big_writing",
                "prompt": (part_b_prompt + " (15 points)") if part_b_prompt else "",
                "source_text": "", "ok": len(part_b_prompt) >= 40})

    # 大作文图表
    chart_path = ""
    if not part_b_prompt:
        # 最后一页是扫描图 → OCR
        try:
            ocr_prompt, chart_path = ocr_ky2_last_page(pdf_path, year)
            if ocr_prompt:
                res[-1]["prompt"] = ocr_prompt
                res[-1]["ok"] = len(ocr_prompt) >= 40
        except Exception as e:
            print(f"    KY2 OCR failed {year}: {e}")
    else:
        try:
            chart_path = crop_ky2_chart(doc, text, year)
        except Exception as e:
            print(f"  chart crop failed for {year}: {e}")
    doc.close()
    res[-1]["chart_image"] = chart_path
    return res


def crop_ky2_chart(doc, text, year):
    """文本型大作文：定位含 Part B 的页，矢量聚类裁剪。"""
    page_idx = None
    for i, pg in enumerate(doc):
        t = re.sub(r"[ \u00a0]+", " ", pg.get_text())
        if re.search(r"Section\s*IV\s*Writing", t, re.IGNORECASE):
            page_idx = i
    if page_idx is None:
        return ""
    out_name = f"ky2_{year}.png"
    out_path = os.path.join(CHART_DIR, out_name)

    for pi in (page_idx, page_idx + 1):
        if pi >= len(doc):
            continue
        pg = doc[pi]
        try:
            clusters = pg.cluster_drawings()
        except Exception:
            clusters = []
        cands = [c for c in clusters if c.width > 140 and c.height > 70]
        if cands:
            rect = max(cands, key=lambda r: r.width * r.height)
            rect = pymupdf.Rect(max(rect.x0 - 10, 0), max(rect.y0 - 10, 0),
                                min(rect.x1 + 10, pg.rect.x1), min(rect.y1 + 10, pg.rect.y1))
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(2.4, 2.4), clip=rect, alpha=False)
            pix.save(out_path)
            return f"charts/{out_name}"
    return ""


# ---------------- 遍历 ----------------

# PDF 缺失部分的人工补录（来源：该场考试公开真题）
MANUAL_OVERRIDES = {
    # 2019.12 六级第2套 PDF 缺写作部分（三套分别为 social/family/community responsibility）
    ("cet6", 2019, 12, 2, "writing"): {
        "prompt": "Directions: For this part, you are allowed 30 minutes to write an essay on the "
                  "importance of having a sense of family responsibility. You should write at least "
                  "150 words but no more than 200 words.",
        "notes": "人工补录：原 PDF 缺写作部分",
    },
}


def main():
    questions = []

    for session in sorted(os.listdir(SIX_DIR)):
        sdir = os.path.join(SIX_DIR, session)
        if not os.path.isdir(sdir):
            continue
        m = re.match(r"(\d{4})年(\d{1,2})月", session)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        for fn in sorted(os.listdir(sdir)):
            if not fn.endswith(".pdf") or "新东方" in fn:
                continue
            sm = re.match(r"第(\d+)套", fn)
            if not sm:
                continue
            set_no = int(sm.group(1))
            pdf_path = os.path.join(sdir, fn)
            print(f"CET6 {year}.{month:02d} 第{set_no}套 ...", flush=True)
            for r in extract_cet6(pdf_path, tag=f"{year}_{month}_{set_no}"):
                rel = os.path.relpath(pdf_path, ROOT)
                ov = MANUAL_OVERRIDES.get(("cet6", year, month, set_no, r["q_type"]))
                if ov:
                    r.update(ov)
                    r["ok"] = True
                questions.append({
                    "exam_type": "cet6", "year": year, "month": month, "set_no": set_no,
                    "title": f"{year}年{month}月六级 第{set_no}套",
                    "source_file": rel, "chart_image": "", **r,
                })

    for ydir in sorted(os.listdir(KY_DIR)):
        kdir = os.path.join(KY_DIR, ydir)
        if not os.path.isdir(kdir):
            continue
        ym = re.match(r"(\d{4})年", ydir)
        if not ym:
            continue
        year = int(ym.group(1))
        pdfs = [f for f in os.listdir(kdir) if f.endswith(".pdf") and "答案" not in f]
        for fn in sorted(pdfs):
            pdf_path = os.path.join(kdir, fn)
            print(f"KY2 {year} ...", flush=True)
            for r in extract_ky2(pdf_path, year):
                questions.append({
                    "exam_type": "ky2", "year": year, "month": 12, "set_no": 1,
                    "title": f"{year}考研英语二",
                    "source_file": os.path.relpath(pdf_path, ROOT),
                    "chart_image": r.pop("chart_image", ""), **r,
                })

    # 经过逐页核实的题干和裁图不再被 OCR 的旧错误覆盖。
    apply_review_to_extracted(questions, ROOT)
    render_reviewed_charts(ROOT, OUT_DIR)
    from scripts.redraw_charts import render_all
    render_all(OUT_DIR)
    out_path = os.path.join(OUT_DIR, "questions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=1)

    bad = [q for q in questions if not q.get("ok")]
    print(f"\n总计 {len(questions)} 题，输出 {out_path}")
    print(f"待人工复核 {len(bad)} 题：")
    for q in bad:
        print("  -", q["exam_type"], q["title"], q["q_type"],
              "prompt_len=", len(q["prompt"]), "src_len=", len(q["source_text"]))


if __name__ == "__main__":
    main()
