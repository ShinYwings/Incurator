from __future__ import annotations

from curator import constants as consts
from curator import llm, secret_store


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


def test_build_client_recovers_when_api_key_env_contains_literal_key():
    client = llm.build_client(
        {
            "llm": {
                "primary": f"{consts.BACKEND_DEEPSEEK_API}::deepseek-v4-flash",
                "fallback": "",
                "primary_effort": "medium",
                consts.BACKEND_DEEPSEEK_API: {
                    "base_url": "https://api.deepseek.com",
                    "api_key_env": "sk-accidentally-saved-as-env-name",
                },
            }
        }
    )

    assert isinstance(client, llm.DeepSeekApiClient)
    assert client.api_key == "sk-accidentally-saved-as-env-name"
    assert client.api_key_env == "DEEPSEEK_API_KEY"


def test_build_client_reads_encrypted_deepseek_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    reference = secret_store.set_secret(secret_store.DEFAULT_DEEPSEEK_SECRET, "secret-key")

    client = llm.build_client(
        {
            "llm": {
                "primary": f"{consts.BACKEND_DEEPSEEK_API}::deepseek-v4-flash",
                "fallback": "",
                "primary_effort": "low",
                consts.BACKEND_DEEPSEEK_API: {
                    "base_url": "https://api.deepseek.com",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "api_key_secret": reference,
                },
            }
        }
    )

    assert isinstance(client, llm.DeepSeekApiClient)
    assert client.api_key == "secret-key"


def test_secret_store_masks_and_deletes_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    reference = secret_store.set_secret("example", "sk-1234567890")

    assert reference == "secret:example"
    assert secret_store.get_secret(reference) == "sk-1234567890"
    assert secret_store.mask_secret(reference) == "sk-1...7890"
    assert secret_store.delete_secret(reference) is True
    assert secret_store.get_secret(reference) == ""
