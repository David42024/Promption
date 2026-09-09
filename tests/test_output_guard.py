"""Output Guard: secretos 100% sintéticos (FAKE_*), nunca valores reales."""
import logging

from src.output_guard import Action, guard_response, scan

FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
FAKE_PK = ("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCFAKEKEYDATA\n"
           "-----END PRIVATE KEY-----")


def test_block_cases():
    assert guard_response("usa api_key=FAKE_API_KEY_9f8e7d6c5b4a como ves").action in (Action.BLOCK, Action.REDACT)
    assert guard_response("config: password=FAKE_PASSWORD_Xy9!q2w").action in (Action.BLOCK, Action.REDACT)
    assert guard_response("Authorization: Bearer FAKE_TOKEN_abc123XYZ789").action in (Action.BLOCK, Action.REDACT)
    assert guard_response(f"tu token es {FAKE_JWT} usalo").action == Action.BLOCK
    assert guard_response(f"clave:\n{FAKE_PK}").action == Action.BLOCK
    assert guard_response("postgresql://svc:FAKE_PW_9x8@db.internal:5432/app").action == Action.BLOCK
    assert guard_response("user: admin password: FAKE_PW_qwerty99").action == Action.BLOCK
    long_resp = ("Claro, te explico el despliegue. " * 20) + " Al final usa api_key=FAKE_API_KEY_Zz12345678 para probar."
    assert guard_response(long_resp).action in (Action.BLOCK, Action.REDACT)
    assert guard_response("Todo bien. password=FAKE_PW_11223344. Saludos.").action in (Action.BLOCK, Action.REDACT)
    assert guard_response("La clave es FAKE_API_KEY_Qq99887766, guárdala bien.").action in (Action.BLOCK, Action.REDACT)


def test_spanish_variants():
    r = guard_response("contraseña=FAKE_CLAVE_12345678 del servicio")
    assert r.action in (Action.BLOCK, Action.REDACT)
    assert guard_response("api_key = FAKE_API_KEY_1234567890").action in (Action.BLOCK, Action.REDACT)


def test_pass_cases():
    assert guard_response("Una API key permite autenticar una aplicación.").action == Action.PASS
    assert guard_response("Debes almacenar las contraseñas utilizando hashing.").action == Action.PASS
    assert guard_response("Un JWT contiene tres partes separadas por puntos.").action == Action.PASS
    assert guard_response("¿Qué diferencia existe entre un token y una sesión?").action == Action.PASS
    assert guard_response("Pon API_KEY=<YOUR_API_KEY> en tu .env de ejemplo.").action == Action.PASS
    assert guard_response("Usa PASSWORD=${PASSWORD} y process.env.API_KEY en el tutorial.").action == Action.PASS
    assert guard_response("Ejemplo: os.getenv(\"API_KEY\") sin valor real.").action == Action.PASS
    assert guard_response("Guía de autenticación: usa hashing, sal y gestores de claves.").action == Action.PASS


def test_redact_preserves_context():
    r = guard_response("La configuración utiliza API key FAKE_API_KEY_Zz12345678 para autenticarse.")
    assert r.action in (Action.BLOCK, Action.REDACT)
    if r.action == Action.REDACT:
        assert "FAKE_API_KEY_Zz12345678" not in (r.redacted_response or "")
        assert "[REDACTED]" in (r.redacted_response or "")
        assert "autenticarse" in (r.redacted_response or "")


def test_block_message_has_no_secret():
    from src.output_guard.redactor import BLOCK_MESSAGE
    guard_response(f"filtra esto: {FAKE_JWT}")
    assert "eyJhbGci" not in BLOCK_MESSAGE


def test_result_structure():
    r = guard_response("nada sensible aquí, solo texto normal.")
    d = r.to_dict()
    assert d == {"action": "PASS", "risk": 0.02, "categories": [], "matches": 0, "redacted_response": None}
    r2 = guard_response(f"key: {FAKE_JWT}")
    assert r2.to_dict()["categories"] == ["jwt"] and r2.to_dict()["matches"] >= 1


def test_logs_never_contain_secrets(caplog):
    secret = "FAKE_API_KEY_SUPERSECRETA_1234567890"
    with caplog.at_level(logging.INFO, logger="pif"):
        guard_response(f"usa api_key={secret} ya")
    assert secret not in caplog.text
    assert "api_key" in caplog.text  # la categoría sí se registra


def test_scan_is_deterministic_and_local():
    a = [(f.category, f.severity) for f in scan("password=FAKE_PW_abcdef1234")]
    b = [(f.category, f.severity) for f in scan("password=FAKE_PW_abcdef1234")]
    assert a == b and a
