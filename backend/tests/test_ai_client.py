"""ai_client 的 URL 规整与请求体定制的单元测试。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_client import build_url, _extra_payload


def test_build_url_bare_host():
    assert build_url("https://api.deepseek.com") == "https://api.deepseek.com/v1/chat/completions"
    assert build_url("https://api.deepseek.com/") == "https://api.deepseek.com/v1/chat/completions"


def test_build_url_version_paths():
    assert build_url("https://open.bigmodel.cn/api/paas/v4") == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert build_url("https://opencode.ai/zen/go/v1") == "https://opencode.ai/zen/go/v1/chat/completions"
    assert build_url("https://example.com/v1") == "https://example.com/v1/chat/completions"


def test_build_url_full_path_passthrough():
    assert build_url("https://x.com/v1/chat/completions") == "https://x.com/v1/chat/completions"
    assert build_url("https://open.bigmodel.cn/api/paas/v4/chat/completions") == \
        "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def test_extra_payload_glm4_thinking_disabled():
    p = {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4.6"}
    assert _extra_payload(p) == {"thinking": {"type": "disabled"}}


def test_extra_payload_glm5_forced_thinking_not_disabled():
    # glm-5.x 强制思考，传 disabled 会 400，必须不附加
    for model in ("glm-5.3-flash", "glm-5.3", "GLM-5.3-Flash"):
        p = {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": model}
        assert _extra_payload(p) == {}, model
    p2 = {"base_url": "https://opencode.ai/zen/go/v1", "model": "glm-5.3-flash"}
    assert _extra_payload(p2) == {}


def test_extra_payload_no_extra_for_deepseek():
    p = {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"}
    assert _extra_payload(p) == {}
    p2 = {"base_url": "https://api.openai.com/v1", "model": "gpt-4o"}
    assert _extra_payload(p2) == {}
