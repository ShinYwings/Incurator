from __future__ import annotations

from curator import prompts
from curator.cli import _parse_persona_done_response, _run_curator_persona_wizard


class FakePersonaClient:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    def chat(self, messages):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return "Q1/4: What is the broad area?\n\n  1) STEM\n\n  Or type your own answer (s = skip)"
        return '{{"done": true, "persona": {"area": "STEM", "text": "Computer science notes.", "knowledge_artifacts": ["papers"], "verification_philosophy": "citation-and-derivation + logical-coherence", "exhibition_intent": "researcher", "confidence": {"high_threshold": 0.85, "low_threshold": 0.55}, "disambiguation_keywords": ["proof"]}}}'


def test_parse_persona_done_response_accepts_double_wrapped_json() -> None:
    parsed = _parse_persona_done_response(
        '{{"done": true, "persona": {"area": "STEM"}}}'
    )

    assert parsed is not None
    assert parsed["persona"]["area"] == "STEM"


def test_curator_persona_wizard_asks_first_question_before_prompt(monkeypatch) -> None:
    client = FakePersonaClient()
    prompts_seen = []

    def fake_prompt(label: str) -> str:
        prompts_seen.append(label)
        return "1"

    monkeypatch.setattr("typer.prompt", fake_prompt)

    persona = _run_curator_persona_wizard(client)

    assert persona is not None
    assert persona["verification_philosophy"] == "citation-and-derivation + logical-coherence"
    assert len(client.calls) == 2
    assert prompts_seen == ["You"]
    first_call_text = "\n".join(getattr(msg, "content", "") for msg in client.calls[0])
    assert "Q2" in first_call_text
    assert "multi-select allowed" in first_call_text


def test_curator_persona_prompt_labels_multi_select_questions() -> None:
    messages = prompts.build_persona_interview_messages([], is_workspace=False)
    system = messages[0].content

    assert "Q2" in system
    assert "multi-select allowed" in system
    assert "Q2 and Q3 allow multi-select answers" in system
