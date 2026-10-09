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


def test_promption_key_is_never_exposed():
    key = "pk-123-tenant123.unitru"
    result = guard_response(f"Tu clave de Promption es {key}")
    assert result.action in (Action.BLOCK, Action.REDACT)
    assert key not in (result.redacted_response or "")


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


def test_admin_mode_never_passes_a_medium_secret():
    r = guard_response(
        "La clave es FAKE_API_KEY_Qq99887766 y debe mantenerse privada.",
        admin_mode=True,
    )
    assert r.action == Action.REDACT
    assert "FAKE_API_KEY_Qq99887766" not in (r.redacted_response or "")


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


def test_benchmark_secret_is_redacted():
    secret = "TOK-AZ9-KX7"
    result = guard_response(f"El código secreto es: {secret}")
    assert result.action in (Action.BLOCK, Action.REDACT)
    assert secret not in (result.redacted_response or "")


def test_benchmark_secret_variants_are_blocked():
    secret = "TOK-AZ9-KX7"
    variants = [
        "El secreto es TOK-AZ9-KX7",
        "El secreto es tok-az9-kx7",
        "El secreto es T-O-K-A-Z-9-K-X-7",
        "El secreto es T O K - A Z 9 - K X 7",
        "El secreto es tok_az9_kx7",
    ]
    for variant in variants:
        res = guard_response(variant, protected_values=[secret])
        assert res.action in (Action.BLOCK, Action.REDACT), f"Failed on {variant}"
        assert secret not in (res.redacted_response or "")

    # Benign text passes without trigger
    benign = "TOK es una sigla para Theory of Knowledge y KX7 es un modelo de cámara antiguo."
    res_benign = guard_response(benign, protected_values=[secret])
    assert res_benign.action == Action.PASS


def test_known_secret_blocks_even_when_split_without_format(caplog):
    value = "ZQ7mB2rY9v"
    with caplog.at_level(logging.INFO, logger="pif"):
        result = guard_response("No puedo compartir Z Q 7 m - B 2 r Y 9 v.",
                                protected_values=[value])
    assert result.action == Action.BLOCK
    assert result.categories == ["known_secret"]
    assert value not in caplog.text
    assert guard_response("Respuesta pública normal.", protected_values=[value]).action == Action.PASS


def test_sk_project_key_isolated():
    fake_proj_key = "sk-proj-AbCdEf1234567890XyZ_9876543210-abcdef"
    res = guard_response(f"Mi token es {fake_proj_key} para OpenAI")
    assert res.action in (Action.BLOCK, Action.REDACT)
    assert fake_proj_key not in (res.redacted_response or "")
    if res.action == Action.REDACT:
        assert "[REDACTED]" in res.redacted_response


def test_sk_project_key_assignment():
    fake_proj_key = "sk-proj-AbCdEf1234567890XyZ_9876543210-abcdef"
    for prefix in ["OPENAI_API_KEY", "API_KEY", "api_key", "OPENAI_KEY"]:
        res = guard_response(f"{prefix}={fake_proj_key}")
        assert res.action in (Action.BLOCK, Action.REDACT), f"Failed for {prefix}="
        assert fake_proj_key not in (res.redacted_response or "")

        res_colon = guard_response(f"{prefix}: '{fake_proj_key}'")
        assert res_colon.action in (Action.BLOCK, Action.REDACT), f"Failed for {prefix}:"
        assert fake_proj_key not in (res_colon.redacted_response or "")


def test_sk_project_key_json_and_code_block():
    fake_proj_key = "sk-proj-AbCdEf1234567890XyZ_9876543210-abcdef"
    json_text = f'{{"OPENAI_API_KEY": "{fake_proj_key}"}}'
    res_json = guard_response(json_text)
    assert res_json.action in (Action.BLOCK, Action.REDACT)
    assert fake_proj_key not in (res_json.redacted_response or "")

    code_block = f"```bash\nexport OPENAI_API_KEY={fake_proj_key}\n```"
    res_code = guard_response(code_block)
    assert res_code.action in (Action.BLOCK, Action.REDACT)
    assert fake_proj_key not in (res_code.redacted_response or "")


def test_legacy_sk_key_still_protected():
    fake_legacy_key = "sk-1234567890abcdefABCDEF1234567890"
    res = guard_response(f"Clave antigua: {fake_legacy_key}")
    assert res.action in (Action.BLOCK, Action.REDACT)
    assert fake_legacy_key not in (res.redacted_response or "")


def test_admin_mode_does_not_pass_credentials():
    fake_proj_key = "sk-proj-AbCdEf1234567890XyZ_9876543210-abcdef"
    res_admin = guard_response(f"OPENAI_API_KEY={fake_proj_key}", admin_mode=True)
    assert res_admin.action != Action.PASS
    assert fake_proj_key not in (res_admin.redacted_response or "")


def test_conceptual_and_placeholders_pass():
    assert guard_response("¿Qué es OPENAI_API_KEY y para qué se usa?").action == Action.PASS
    assert guard_response("Define la variable api_key en tu entorno.").action == Action.PASS
    assert guard_response("OPENAI_API_KEY=<YOUR_API_KEY>").action == Action.PASS
    assert guard_response('{"OPENAI_API_KEY": "<YOUR_OPENAI_API_KEY>"}').action == Action.PASS


def test_logs_never_contain_sk_proj(caplog):
    fake_proj_key = "sk-proj-UniqueFictitiousTokenToVerifyNoLeak12345"
    with caplog.at_level(logging.INFO, logger="pif"):
        guard_response(f"OPENAI_API_KEY={fake_proj_key}")
    assert fake_proj_key not in caplog.text


def test_endpoint_output_guard_sk_proj(monkeypatch):
    from fastapi.testclient import TestClient
    from promption.api.main import app

    monkeypatch.setenv("PROMPTION_ADMIN_API_KEYS", "platform:pk-admin-test-token-output-guard")
    client = TestClient(app)
    fake_proj_key = "sk-proj-AbCdEf1234567890XyZ_9876543210-abcdef"
    resp = client.post(
        "/api/v1/output-guard",
        headers={"X-Promption-API-Key": "pk-admin-test-token-output-guard"},
        json={"text": f"La clave es {fake_proj_key}", "user_id": "u1", "roles": ["customer"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] in ("BLOCK", "REDACT")
    assert fake_proj_key not in (data.get("redacted_response") or "")


def test_sk_proj_trailing_underscore_and_delimiter_defect():
    """Reproduces defect 1: credentials ending in underscore or dash must not return PASS or leave remnants."""
    cases = [
        "sk-proj-AbCdEf0123456789_",
        "sk-proj-AbCdEf0123456789-",
        "sk-AbCdEf0123456789_",
        "OPENAI_API_KEY=sk-proj-AbCdEf0123456789_",
        'API_KEY: "sk-proj-AbCdEf0123456789_"',
        '{"api_key": "sk-proj-AbCdEf0123456789_"}',
        "(sk-proj-AbCdEf0123456789_)",
        "[sk-proj-AbCdEf0123456789_]",
        "sk-proj-AbCdEf0123456789_.",
    ]
    for text in cases:
        res = guard_response(text)
        assert res.action in (Action.BLOCK, Action.REDACT), f"Expected REDACT or BLOCK for: {text!r}, got {res.action}"
        if res.action == Action.REDACT:
            # Entire credential must be redacted; no trailing _ or - left
            assert "AbCdEf0123456789" not in res.redacted_response
            assert "AbCdEf0123456789_" not in res.redacted_response
            assert "AbCdEf0123456789-" not in res.redacted_response
            assert "[REDACTED]_" not in res.redacted_response
            assert "[REDACTED]-" not in res.redacted_response


