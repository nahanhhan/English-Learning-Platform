"""统一自然女声、朗读文本规范化与可跨重启使用的完整音频缓存。"""
import asyncio
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..database import DATA_DIR

RULE_VERSION = "speech-text-v1"
VOICES = {"us": "en-US-JennyNeural", "uk": "en-GB-SoniaNeural"}
RATE = "-5%"
PITCH = "+0Hz"


class SpeechUnavailable(Exception):
    pass


def normalize_speech_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("’", "'")
    text = re.sub(r"\b(sb|sth)\b\.?", lambda match: "somebody" if match[1].lower() == "sb" else "something",
                  text, flags=re.IGNORECASE)
    text = text.replace("/", " or ")
    text = re.sub(r"[()（）]", " ", text)
    # 词典的省略号、OCR 控制字符不是需要逐字拼读的词。
    text = re.sub(r"\.{2,}|…+|[\x00-\x1f\x7f]", " ", text)
    return " ".join(text.split())


def cache_key(text: str, accent: str) -> str:
    profile = [RULE_VERSION, text, VOICES[accent], RATE, PITCH]
    return hashlib.sha256(json.dumps(profile, ensure_ascii=False).encode("utf-8")).hexdigest()


def valid_mp3(data: bytes) -> bool:
    return len(data) >= 256 and (data.startswith(b"ID3") or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0))


def cached_file(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            head = file.read(256)
        return valid_mp3(head)
    except OSError:
        return False


@dataclass(frozen=True)
class SpeechAudio:
    path: Path
    voice: str
    cached: bool


class SpeechService:
    def __init__(self, cache_dir: Path, synthesizer=None, timeout: float = 25):
        self.cache_dir = Path(cache_dir)
        self.synthesizer = synthesizer or self._edge_synthesize
        self.timeout = timeout
        self._inflight: dict[str, asyncio.Task] = {}
        self._slots = asyncio.Semaphore(2)

    async def audio(self, text: str, accent: str = "us") -> SpeechAudio:
        spoken = normalize_speech_text(text)
        if not spoken:
            raise ValueError("请输入需要朗读的英文")
        if accent not in VOICES:
            raise ValueError("请选择美式或英式发音")
        key = cache_key(spoken, accent)
        path = self.cache_dir / f"{key}.mp3"
        if cached_file(path):
            return SpeechAudio(path, VOICES[accent], True)
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._generate(spoken, VOICES[accent], path))
            self._inflight[key] = task
            def complete(done):
                if self._inflight.get(key) is done:
                    self._inflight.pop(key, None)
                # 请求全部取消时也取回异常，避免无人等待的任务输出错误。
                if not done.cancelled():
                    done.exception()
            task.add_done_callback(complete)
        # 浏览器切题不会取消其他正在等待同一音频的请求。
        await asyncio.shield(task)
        return SpeechAudio(path, VOICES[accent], False)

    async def _generate(self, text: str, voice: str, path: Path):
        try:
            async with self._slots:
                data = await asyncio.wait_for(self.synthesizer(text, voice, RATE, PITCH), self.timeout)
            if not valid_mp3(data):
                raise SpeechUnavailable("没有收到完整的语音音频")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.cache_dir, suffix=".part", delete=False) as file:
                    temporary = Path(file.name)
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise SpeechUnavailable("发音暂时不可用，请稍后点击发音按钮重试") from exc

    @staticmethod
    async def _edge_synthesize(text: str, voice: str, rate: str, pitch: str) -> bytes:
        from edge_tts import Communicate
        # 整个词条在一次调用中生成，保留自然语调，不拼接不同录音。
        chunks = []
        async for chunk in Communicate(text, voice, rate=rate, pitch=pitch).stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)


speech_service = SpeechService(Path(DATA_DIR) / "speech-cache")


def get_speech_service() -> SpeechService:
    return speech_service
