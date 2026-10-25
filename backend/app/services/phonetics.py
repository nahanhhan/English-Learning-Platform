"""使用本地 CMU 美式发音词典；不调用网络，也不从普通英式音标猜测。"""
import re
from functools import lru_cache

# 教材的英式拼写与美式等价词；复合词按词组查询。
ALIASES = {"omelette": "omelet", "wilful": "willful", "back-burner": "back burner"}
# 少量词典缺词的补充，来源留在代码中以便核对。
SUPPLEMENTS = {
    # https://dictionary.cambridge.org/us/dictionary/english/knackered
    "knackered": "ˈnæk.ɚd",
    # Collins toboggan 的美式词干及其 -ist 派生词：
    # https://www.collinsdictionary.com/us/dictionary/english/toboggan
    "tobogganist": "təˈbɑɡənɪst",
}


def american_ipa(english: str) -> str:
    return _lookup(" ".join((english or "").strip().lower().split()))


@lru_cache(maxsize=8192)
def _lookup(word: str) -> str:
    if not word or not re.fullmatch(r"[a-z]+(?:[-' ][a-z]+)*", word):
        return ""
    if word in SUPPLEMENTS:
        return SUPPLEMENTS[word]
    from eng_to_ipa import convert
    result = convert(ALIASES.get(word, word), keep_punct=False)
    return result.strip() if result and "*" not in result else ""
