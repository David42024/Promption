"""A refusal is safe to deliver unless it also exposes a secret."""

import pytest

from src.output_guard import Action, guard_response, scan


@pytest.mark.parametrize("text", [
    "Lo siento, no puedo ayudar con eso.",
    "No tengo información sobre ese plazo.",
    "No tengo permiso para compartir esos datos.",
    "I'm sorry, but I cannot help with that.",
    "I don't have permission to share those details.",
])
def test_legitimate_refusal_passes(text):
    assert guard_response(text).action == Action.PASS
    assert not any(f.category == "refusal" for f in scan(text))


def test_refusal_containing_secret_is_still_guarded():
    secret = "J3f3-2026*-!AdminRoot"
    result = guard_response(f"No puedo revelar la contraseña admin: {secret}")
    assert result.action in {Action.REDACT, Action.BLOCK}
    assert "password" in result.categories
    assert secret not in (result.redacted_response or "")
