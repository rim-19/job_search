"""LLM JSON extraction (fenced / messy) — deterministic via monkeypatch."""
from src import gemini


def test_generate_json_fenced(monkeypatch):
    monkeypatch.setattr(gemini, "generate",
                        lambda *a, **k: '```json\n{"score": 80, "priority": "APPLY"}\n```')
    out = gemini.generate_json("x")
    assert out["score"] == 80 and out["priority"] == "APPLY"


def test_generate_json_messy_prose(monkeypatch):
    monkeypatch.setattr(gemini, "generate",
                        lambda *a, **k: 'Sure! Here you go: {"score": 70} hope that helps')
    assert gemini.generate_json("x")["score"] == 70


def test_generate_json_plain(monkeypatch):
    monkeypatch.setattr(gemini, "generate", lambda *a, **k: '{"eligible": false, "score": 20}')
    out = gemini.generate_json("x")
    assert out["eligible"] is False and out["score"] == 20
