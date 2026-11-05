import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.phonetics import american_ipa


def test_american_ipa_is_offline_normalized_and_marks_unknown():
    assert american_ipa(" BEARER ") == american_ipa("bearer")
    assert american_ipa("bearer") and "r" in american_ipa("bearer")
    assert "oʊ" in american_ipa("go")
    assert american_ipa("unknownclassroomzzzzz") == ""
    assert american_ipa("") == ""


def test_all_initial_classroom_words_have_american_phonetics():
    path = Path(__file__).resolve().parent.parent / "data/classroom_initial.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [english for group in data["groups"] for english, _ in group["words"] if not american_ipa(english)]
    assert missing == []


def test_british_spelling_keeps_same_american_pronunciation():
    assert american_ipa("omelette") == american_ipa("omelet")
    assert american_ipa("wilful") == american_ipa("willful")


def test_accumulation_missing_american_pronunciations_are_offline_available():
    assert american_ipa('benefaction') == 'ˌben.əˈfæk.ʃən'
    assert american_ipa('lamentation') == 'ˌlæm.enˈteɪ.ʃən'
    assert american_ipa('would-be') == 'ˈwʊd.bi'
    assert american_ipa('ill-reputed') == american_ipa('ill reputed')
    assert american_ipa('ill-reputed')
    paths = (Path(__file__).resolve().parent.parent / 'data').glob('accumulation*.json')
    missing = []
    for path in paths:
        for group in json.loads(path.read_text(encoding='utf-8'))['groups']:
            missing.extend(e['english'] for e in group['entries']
                if e['item_type'] == 'word' and not american_ipa(e['english']))
    assert missing == []
