from __future__ import annotations

from curator import constants as consts
from curator import llm


def test_build_client_supports_deepseek_api(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = llm.build_client(
        {
            "llm": {
                "primary": f"{consts.BACKEND_DEEPSEEK_API}::deepseek-v4-flash",
                "fallback": "",
                "primary_effort": "medium",
                consts.BACKEND_DEEPSEEK_API: {
                    "base_url": "https://api.deepseek.com",
                    "api_key_env": "DEEPSEEK_API_KEY",
                },
            }
        }
    )

    assert isinstance(client, llm.DeepSeekApiClient)
    assert client.model == "deepseek-v4-flash"
    assert client.api_key == "test-key"


def test_deepseek_body_uses_openai_compatible_messages(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = llm.DeepSeekApiClient(model="deepseek-v4-pro", effort="high")
    body = client._body(
        [llm.ChatMessage(role="user", content="hello")],
        json_mode=True,
        temperature=0.2,
        stream=False,
    )

    assert body["model"] == "deepseek-v4-pro"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "high"
    assert body["thinking"] == {"type": "enabled"}
