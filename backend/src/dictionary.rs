use crate::{api::text, db};
use flate2::read::GzDecoder;
use regex::Regex;
use rusqlite::{Connection, OpenFlags};
use serde_json::Value;
use std::{
    collections::HashMap,
    fs::File,
    path::Path,
    sync::{Mutex, OnceLock},
};

fn extract(input: &str, definition: bool) -> String {
    static MARKER: OnceLock<Regex> = OnceLock::new();
    static DICTIONARY_PREFIX: OnceLock<Regex> = OnceLock::new();
    let marker = MARKER.get_or_init(|| Regex::new(
        r"(?i)(?:^|[\n；;,，/&])\s*(?:\[[^\]\n]+\]\s*)?(aux\.\s*v|v\.\s*aux|v\.\s*t|v\.\s*i|interj|modal|adj|adv|prep|pron|conj|num|det|art|aux|vt|vi|int|ad|[nvasir])\."
    ).unwrap());
    let input = input.replace("\\n", "\n");
    let input = if definition {
        DICTIONARY_PREFIX
            .get_or_init(|| Regex::new(r"(?m)^([nvasr])(\s)").unwrap())
            .replace_all(&input, "$1.$2")
            .into_owned()
    } else {
        input
    };
    let mut tokens = Vec::new();
    for matched in marker.captures_iter(&input) {
        let end = matched.get(0).unwrap().end();
        if input[end..].chars().next().is_some_and(|c| {
            !(c.is_whitespace() || ('\u{3400}'..='\u{9fff}').contains(&c) || ",，/&".contains(c))
        }) {
            continue;
        }
        let token: String = matched[1]
            .to_lowercase()
            .chars()
            .filter(|c| !c.is_whitespace())
            .collect();
        let kind = match token.as_str() {
            "a" | "s" => "adj",
            "r" | "ad" => "adv",
            "i" | "int" => "interj",
            "v.t" => "vt",
            "v.i" => "vi",
            "aux.v" | "v.aux" => "aux",
            _ => token.as_str(),
        };
        let label = format!("{kind}.");
        if !tokens.contains(&label) {
            tokens.push(label);
        }
    }
    tokens.join(" / ")
}

pub fn parts(data: &Path, english: &str, translation: &str, definition: &str) -> String {
    static FALLBACK: OnceLock<HashMap<String, String>> = OnceLock::new();
    let by_meaning = extract(translation, false);
    if !by_meaning.is_empty() {
        return by_meaning;
    }
    let by_definition = extract(definition, true);
    if !by_definition.is_empty() {
        return by_definition;
    }
    FALLBACK
        .get_or_init(|| {
            let mut result = HashMap::new();
            if let Ok(Value::Object(books)) = db::load_json(data, "words.json") {
                for word in books.values().filter_map(Value::as_array).flatten() {
                    let mut value = extract(text(word, "translation"), false);
                    if value.is_empty() {
                        value = extract(text(word, "definition"), true);
                    }
                    if !value.is_empty() {
                        result.insert(db::normalize(text(word, "headword")), value);
                    }
                }
            }
            if let Ok(value) = db::load_json(data, "classroom_parts_of_speech.json") {
                if let Some(words) = value["words"].as_object() {
                    for (word, value) in words {
                        if let Some(kind) = value.as_str() {
                            result.insert(word.clone(), kind.to_owned());
                        }
                    }
                }
            }
            result
        })
        .get(&db::normalize(english))
        .cloned()
        .unwrap_or_default()
}

pub fn definitions(data: &Path, english: &str) -> (Vec<String>, String) {
    static WORDNET: OnceLock<HashMap<String, Vec<String>>> = OnceLock::new();
    let english = db::normalize(english);
    let supplement = match english.as_str() {
        "sheerly" => Some(("in an utter or pure manner", "sheer")),
        "absent-mindedly" => Some((
            "in a way that shows a lack of attention to one's surroundings or actions",
            "absentminded",
        )),
        "-tempered" => Some((
            "having the kind of temperament specified by the preceding word",
            "tempered",
        )),
        "hooded" => Some(("wearing or having a hood", "hooded")),
        "back-burner" => Some((
            "given a lower priority and set aside for later consideration",
            "back%20burner",
        )),
        _ => None,
    };
    if let Some((meaning, link)) = supplement {
        return (
            vec![meaning.to_owned()],
            format!("https://www.merriam-webster.com/dictionary/{link}"),
        );
    }
    let words = WORDNET.get_or_init(|| {
        File::open(data.join("wordnet-definitions.json.gz"))
            .ok()
            .and_then(|file| serde_json::from_reader(GzDecoder::new(file)).ok())
            .unwrap_or_default()
    });
    (
        words.get(&english).cloned().unwrap_or_default(),
        String::new(),
    )
}

pub fn ipa(data: &Path, english: &str) -> String {
    static CMU: OnceLock<Mutex<Option<Connection>>> = OnceLock::new();
    static SPELLING: OnceLock<Regex> = OnceLock::new();
    let normalized = db::normalize(english);
    let english = match normalized.as_str() {
        "omelette" => "omelet",
        "wilful" => "willful",
        "back-burner" => "back burner",
        "ill-reputed" => "ill reputed",
        "-tempered" => "tempered",
        other => other,
    };
    let supplement = match english {
        "knackered" => "ˈnæk.ɚd",
        "tobogganist" => "təˈbɑɡənɪst",
        "benefaction" => "ˌben.əˈfæk.ʃən",
        "lamentation" => "ˌlæm.enˈteɪ.ʃən",
        "would-be" => "ˈwʊd.bi",
        "sheerly" => "ˈʃɪrli",
        "pessimistically" => "ˌpɛsəˈmɪstɪkli",
        "fatefully" => "ˈfeɪtfəli",
        "absent-mindedly" => "ˌæbsəntˈmaɪndɪdli",
        "resignedly" => "rɪˈzaɪnɪdli",
        "gaiety" => "ˈɡeɪɪti",
        _ => "",
    };
    if !supplement.is_empty() {
        return supplement.to_owned();
    }
    if !SPELLING
        .get_or_init(|| Regex::new(r"^[a-z]+(?:[-' ][a-z]+)*$").unwrap())
        .is_match(english)
    {
        return String::new();
    }
    let access = CMU.get_or_init(|| {
        let path = data.join("../.venv/Lib/site-packages/eng_to_ipa/resources/CMU_dict.db");
        Mutex::new(Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY).ok())
    });
    let Ok(access) = access.lock() else {
        return String::new();
    };
    let Some(db) = access.as_ref() else {
        return String::new();
    };
    english
        .split_whitespace()
        .map(|word| {
            db::rows(db, "SELECT phonemes FROM dictionary WHERE word=?1", [word])
                .ok()?
                .iter()
                .map(|entry| phonemes(text(entry, "phonemes")))
                .max()
        })
        .collect::<Option<Vec<_>>>()
        .map(|words| words.join(" "))
        .unwrap_or_default()
}

fn phonemes(input: &str) -> String {
    let phones: Vec<_> = input.split_whitespace().collect();
    let base = |phone: &str| phone.trim_end_matches(['0', '1', '2']).to_owned();
    let is_vowel = |phone: &str| {
        matches!(
            phone,
            "aa" | "ae"
                | "ah"
                | "ao"
                | "aw"
                | "ay"
                | "eh"
                | "er"
                | "ey"
                | "ih"
                | "iy"
                | "ow"
                | "oy"
                | "uh"
                | "uw"
        )
    };
    let stop = |phone: &str| matches!(phone, "b" | "d" | "g" | "k" | "p" | "t");
    let boundary = |phone: &str| {
        is_vowel(phone)
            || matches!(
                phone,
                "m" | "n" | "ng" | "dh" | "f" | "s" | "sh" | "th" | "v" | "z" | "zh" | "w" | "j"
            )
    };
    let bases: Vec<_> = phones.iter().map(|phone| base(phone)).collect();
    let multi = bases
        .iter()
        .enumerate()
        .filter(|(i, phone)| {
            if !is_vowel(phone) {
                return false;
            }
            let prev = i
                .checked_sub(1)
                .map(|index| bases[index].as_str())
                .unwrap_or("");
            !is_vowel(prev)
                || matches!(
                    (prev, phone.as_str()),
                    ("er", "iy" | "eh") | ("iy", "ow" | "ah" | "ey") | ("uw", "ow" | "eh")
                )
        })
        .count()
        > 1;
    let mut output: Vec<(String, &str)> = Vec::new();
    for (index, phone) in phones.iter().enumerate() {
        let base = phone.trim_end_matches(['0', '1', '2']);
        let letter = match base {
            "ey" => "eɪ",
            "aa" => "ɑ",
            "ae" => "æ",
            "ah" | "a" => "ə",
            "ao" => "ɔ",
            "aw" => "aʊ",
            "ay" => "aɪ",
            "ch" => "ʧ",
            "dh" => "ð",
            "eh" => "ɛ",
            "er" => "ər",
            "hh" => "h",
            "ih" => "ɪ",
            "jh" => "ʤ",
            "ng" => "ŋ",
            "ow" => "oʊ",
            "oy" => "ɔɪ",
            "sh" => "ʃ",
            "th" => "θ",
            "uh" => "ʊ",
            "uw" => "u",
            "zh" => "ʒ",
            "iy" => "i",
            "y" => "j",
            other => other,
        };
        let mut letter = letter.to_owned();
        if multi && phone.ends_with(['1', '2']) {
            let stress = if phone.ends_with('1') { 'ˈ' } else { 'ˌ' };
            let onset = if index == 0 {
                None
            } else {
                (0..index)
                    .rev()
                    .find_map(|pos| {
                        let current = output[pos].1;
                        let following = output.get(pos + 1).map_or(output[0].1, |part| part.1);
                        if !boundary(current) && !(pos + 1 < index && stop(following)) {
                            return None;
                        }
                        let cluster = matches!(
                            (current, following),
                            ("s", "p" | "t" | "k") | ("f", "r" | "l")
                        );
                        Some(if cluster {
                            Some(pos)
                        } else if pos + 1 < index && !is_vowel(following) {
                            Some(pos + 1)
                        } else if is_vowel(current) {
                            None
                        } else {
                            Some(pos)
                        })
                    })
                    .unwrap_or(Some(0))
            };
            if let Some(onset) = onset {
                output[onset].0.insert(0, stress);
            } else {
                letter.insert(0, stress);
            }
        }
        output.push((letter, base));
    }
    let mut word: String = output.into_iter().map(|(word, _)| word).collect();
    for (from, to) in [("ˈər", "əˈr"), ("ˈie", "iˈe")] {
        if !word.starts_with(from) {
            word = word.replace(from, to);
        }
    }
    word
}
