"""按需调用现有的文件识别和自然发音引擎。"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    action, option = sys.argv[1:3]
    data = sys.stdin.buffer.read()
    if action == "document":
        from app.services.classroom import ClassroomError
        from app.services.classroom_import import extract_file

        try:
            return extract_file(data, option), 0
        except ClassroomError as error:
            return {"detail": str(error), "status": error.status}, 1
    if action == "speech":
        from app.services.speech import SpeechUnavailable, get_speech_service

        try:
            asyncio.run(get_speech_service().audio(data.decode("utf-8"), option))
            return {"ok": True}, 0
        except ValueError as error:
            return {"detail": str(error), "status": 400}, 1
        except SpeechUnavailable as error:
            return {"detail": str(error), "status": 503}, 1
    return {"detail": "媒体处理任务无效", "status": 400}, 1


if __name__ == "__main__":
    result, status = main()
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    raise SystemExit(status)
