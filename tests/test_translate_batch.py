"""Armado/parseo de lotes de traducción (offline, sin red)."""
from scripts.translate_batch import build_prompt, parse_response


def test_build_prompt_numbers_batch():
    p = build_prompt(["Hello", "Bye"])
    assert "1. Hello" in p and "2. Bye" in p
    assert "JSON" in p


def test_parse_response_json_array():
    data = {"candidates": [{"content": {"parts": [{"text": '["Hola", "Adiós"]'}]}}]}
    assert parse_response(data, 2) == ["Hola", "Adiós"]


def test_parse_response_rejects_wrong_count():
    data = {"candidates": [{"content": {"parts": [{"text": '["Solo una"]'}]}}]}
    assert parse_response(data, 2) == []


def test_parse_response_empty():
    assert parse_response({}, 3) == []
