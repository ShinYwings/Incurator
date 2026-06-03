import json
import base64
from pathlib import Path
from curator import llm_identity, constants as consts


def test_decode_jwt_claims():
    payload = json.dumps({"email": "test@test.com", "name": "Tester"}).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    token = f"header.{encoded_payload}.signature"
    claims = llm_identity._decode_jwt_claims(token)
    assert claims["email"] == "test@test.com"
    assert claims["name"] == "Tester"


def test_get_llm_account_info_ollama():
    info = llm_identity.get_llm_account_info(consts.BACKEND_OLLAMA)
    assert info["provider"] == consts.BACKEND_OLLAMA
    assert info["name"] == "Local (no account)"
    assert info["email"] is None


def test_get_llm_account_info_deepseek():
    info = llm_identity.get_llm_account_info(consts.BACKEND_DEEPSEEK_API)
    assert info["provider"] == consts.BACKEND_DEEPSEEK_API
    assert info["name"] == "API key configured"
    assert info["email"] is None


def test_get_llm_account_info_claude():
    info = llm_identity.get_llm_account_info(consts.BACKEND_CLAUDE_CODE)
    assert info["provider"] == consts.BACKEND_CLAUDE_CODE
    assert info["name"] == "Authenticated (CLI-managed)"
    assert info["email"] is None


def test_get_llm_account_info_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    info = llm_identity.get_llm_account_info(consts.BACKEND_ANTIGRAVITY_CLI)
    assert info["name"] == "Authenticated"
    assert info["email"] is None
