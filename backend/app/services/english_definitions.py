"""本地 WordNet 英文释义；未收录的词不猜测。"""
import gzip
import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "wordnet-definitions.json.gz"

# WordNet 未覆盖的原有课内词，英文注释根据韦氏词典相应词条改写。
SUPPLEMENTS = {
    "sheerly": (["in an utter or pure manner"], "https://www.merriam-webster.com/dictionary/sheer"),
    "absent-mindedly": (["in a way that shows a lack of attention to one's surroundings or actions"], "https://www.merriam-webster.com/dictionary/absentminded"),
    "-tempered": (["having the kind of temperament specified by the preceding word"], "https://www.merriam-webster.com/dictionary/tempered"),
    "hooded": (["wearing or having a hood"], "https://www.merriam-webster.com/dictionary/hooded"),
    "back-burner": (["given a lower priority and set aside for later consideration"], "https://www.merriam-webster.com/dictionary/back%20burner"),
}

@lru_cache(maxsize=1)
def _dictionary():
    with gzip.open(DATA, "rt", encoding="utf-8") as file:
        return json.load(file)

def lookup_definitions(word):
    key = " ".join(word.lower().strip().split())
    return SUPPLEMENTS[key][0] if key in SUPPLEMENTS else _dictionary().get(key, [])

def definition_source(word):
    key = " ".join(word.lower().strip().split())
    return SUPPLEMENTS[key][1] if key in SUPPLEMENTS else ""
