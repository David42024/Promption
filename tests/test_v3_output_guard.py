"""Offline regression tests with fictitious credentials only."""
import pytest
from promption.output_guard import guard_response, Action


@pytest.mark.parametrize("message", [
    "Principios clave: confidencialidad",
    "Indicadores clave: inflación",
    "Conceptos clave: autenticación",
    "Componentes clave: proveedores de nube",
    "Puntos clave: seguridad y administración de identidades",
    "Cloud computing tiene componentes clave: cómputo y redes",
    "La mejor práctica es usar claves privadas, pero nunca compartirlas.",
    "Explica qué significa una contraseña y por qué es importante.",
    "¿Qué diferencia existe entre deep learning y cloud computing?",
])
def test_ordinary_technical_prose_is_not_redacted(message):
    assert guard_response(message).action == Action.PASS


@pytest.mark.parametrize("message,secret", [
    ("password=FAKE_pw_Xy9!q2w77", "FAKE_pw_Xy9!q2w77"),
    ("contraseña: FAKE_Contr4sena_12345", "FAKE_Contr4sena_12345"),
    ("clave privada: FAKE_TOKEN_Zz123456789", "FAKE_TOKEN_Zz123456789"),
    ("clave: FAKE_CLAVE_12345678", "FAKE_CLAVE_12345678"),
    ("La clave es FAKE_API_KEY_Qq99887766", "FAKE_API_KEY_Qq99887766"),
    ("api_key=sk-proj-AbCdEf0123456789XyZ", "sk-proj-AbCdEf0123456789XyZ"),
])
def test_credentials_are_still_protected(message, secret):
    result = guard_response(message)
    assert result.action in (Action.REDACT, Action.BLOCK)
    assert secret not in (result.redacted_response or "")


def test_known_secret_is_blocked_even_in_a_refusal():
    secret = "TOK-AZ9-KX7"
    result = guard_response(f"No puedo revelar el secreto {secret}", protected_values=[secret])
    assert result.action == Action.BLOCK


def test_independent_real_looking_credentials_blocked():
    text = "password=FAKE_pass_12345 and api_key=sk-proj-Zz123456789012345"
    assert guard_response(text).action in (Action.REDACT, Action.BLOCK)


def test_generic_key_needs_a_token_like_value():
    assert guard_response("Tema clave: confidencialidad").action == Action.PASS
    assert guard_response("clave: confidencialidad").action == Action.PASS
    assert guard_response("clave: abcDEF1234567").action == Action.REDACT


def test_punctuated_password_never_leaves_a_visible_suffix():
    secret = "J3f3-2026*-!AdminRoot"
    r = guard_response(f"No puedo revelar la contraseña admin: {secret}")
    assert r.action in (Action.REDACT, Action.BLOCK)
    assert secret not in (r.redacted_response or "")
    assert "AdminRoot" not in (r.redacted_response or "")
    assert "password" in r.categories
