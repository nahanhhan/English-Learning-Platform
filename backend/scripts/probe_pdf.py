"""快速探测真题 PDF 是否为文本型（能否直接抽取文字）"""
import sys
import fitz

targets = [
    r"C:\Users\Nahan\Desktop\English_Learning_Platform\六级\2019年12月\第01套.pdf",
    r"C:\Users\Nahan\Desktop\English_Learning_Platform\六级\2025年12月\第01套.pdf",
    r"C:\Users\Nahan\Desktop\English_Learning_Platform\考研英语二\2020年\2020考研英语二真题.pdf",
    r"C:\Users\Nahan\Desktop\English_Learning_Platform\考研英语二\2026年\2026考研英语二真题.pdf",
]

for path in targets:
    try:
        doc = fitz.open(path)
        total_chars = 0
        snippets = []
        for i, page in enumerate(doc):
            t = page.get_text("text")
            total_chars += len(t)
            if i == 0:
                snippets.append(t[:300].replace("\n", " | "))
        print(f"\n=== {path.split(chr(92))[-3]}/{path.split(chr(92))[-1]}  pages={len(doc)} chars={total_chars}")
        print("P1:", snippets[0][:280] if snippets else "EMPTY")
        doc.close()
    except Exception as e:
        print(f"\n=== {path}: ERROR {e}")
