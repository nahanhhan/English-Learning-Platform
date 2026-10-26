"""从词条释义和本地词库读取词性；不根据单词后缀猜测。"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ALIASES = {
    "a": "adj", "s": "adj", "r": "adv", "ad": "adv", "i": "interj", "int": "interj",
    "v.t": "vt", "v.i": "vi", "aux.v": "aux", "v.aux": "aux",
}
KINDS = {"n", "v", "vt", "vi", "adj", "adv", "prep", "pron", "conj",
         "interj", "num", "det", "art", "aux", "modal"}
# 仅识别行首或释义分隔符后的标记，避免把释义正文中的缩写当成词性。
MARKER = re.compile(
    r"(?:^|[\n；;,，/&])\s*(?:\[[^\]\n]+\]\s*)?"
    r"(aux\.\s*v|v\.\s*aux|v\.\s*t|v\.\s*i|interj|modal|adj|adv|prep|pron|conj|"
    r"num|det|art|aux|vt|vi|int|ad|[nvasir])\.(?=$|\s|[\u3400-\u9fff,，/&])",
    re.IGNORECASE,
)


def extract_parts_of_speech(text: str, *, definition: bool = False) -> str:
    found = []
    text = (text or "").replace("\\n", "\n")
    if definition:
        # ECDICT 英英释义含 WordNet 的无句点行首标记，如 n a forest...。
        text = re.sub(r"(?m)^([nvasr])(?=\s)", r"\1.", text)
    for match in MARKER.finditer(text):
        token = re.sub(r"\s+", "", match[1].lower()).rstrip(".")
        token = ALIASES.get(token, token)
        if token in KINDS and token not in found:
            found.append(token)
    return " / ".join(f"{token}." for token in found)


@lru_cache(maxsize=1)
def _dictionary() -> dict[str, str]:
    # 使用随应用分发的小词库，不依赖未入库的 ECDICT CSV 大文件。
    result = {}
    path = DATA_DIR / "words.json"
    if path.exists():
        for words in json.loads(path.read_text(encoding="utf-8")).values():
            for word in words:
                value = (extract_parts_of_speech(word.get("translation", ""))
                         or extract_parts_of_speech(word.get("definition", ""), definition=True))
                if value:
                    result[word["headword"].strip().casefold()] = value
    path = DATA_DIR / "classroom_parts_of_speech.json"
    if path.exists():
        result.update(json.loads(path.read_text(encoding="utf-8"))["words"])
    return result


def parts_of_speech(english: str, translation: str = "", definition: str = "") -> str:
    # 当前词条的明确标记优先，支持自定义词和导入词在释义中注明 n. / vt. 等。
    return (extract_parts_of_speech(translation) or extract_parts_of_speech(definition, definition=True)
            or _dictionary().get(" ".join((english or "").split()).casefold(), ""))
