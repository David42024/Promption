"""Output Guard: tabla de patrones valor-conscientes (nunca keywords sueltas).

Cada patrón detecta un VALOR sensible en contexto (asignación, formato
estructural, prefijo conocido). Las menciones conceptuales
("¿Qué es una API key?") no calzan porque exigen `=`/`:`/formato.
"""
from __future__ import annotations

PLACEHOLDER_VALUES = {
    "your_api_key", "your_password", "your_token", "your_secret",
    "changeme", "example", "test", "demo", "xxx", "***", "...",
    "test123", "password123",
}

PLACEHOLDER_RE = (
    r"<[^<>\n]{1,40}>|\$\{[A-Za-z_][A-Za-z0-9_]*\}|YOUR_[A-Za-z_]+|"
    r"process\.env\.[A-Za-z_]+|os\.getenv\([\"']?[A-Za-z_]+[\"']?\)|ENV\[[\"']?[A-Za-z_]+[\"']?\]"
)

# (name, category, severity, pattern, confidence, redact_whole_match[, validator])
# validator(value) -> bool extra; "entropy" exige token con letras+dígitos.
PATTERNS: list[tuple] = [
    ("secret_proximity", "api_key", "MEDIUM",
     r"(?i)\b(clave|key|secreto|secret|contrase[ñn]a|password|token|credencial)\b[^.\n]{0,60}?\b([A-Za-z0-9_\-]{12,})\b",
     0.7, False, "entropy"),
    ("private_key_block", "private_key", "CRITICAL",
     r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
     0.99, True),
    ("certificate_block", "private_key", "MEDIUM",
     r"-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----",
     0.6, True),
    ("private_key_lone", "private_key", "HIGH",
     r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
     0.85, True),
    ("connection_string", "connection_string", "CRITICAL",
     r"\b(?:postgresql|postgres|mysql|mongodb(?:\+srv)?|redis|amqp):\/\/[^\s\/]*:[^@\s]{3,}@[^\s]+",
     0.97, True),
    ("connection_generic", "connection_string", "HIGH",
     r"\b[a-z][a-z0-9+.-]{1,20}:\/\/[^:\s\/]{1,40}:[^@\s]{4,}@[^\s]{3,}",
     0.85, True),
    ("jwt", "jwt", "HIGH",
     r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})(?![A-Za-z0-9_.-])",
     0.88, True),
    ("aws_access_key", "cloud", "HIGH", r"\bAKIA[0-9A-Z]{16}\b", 0.95, True),
    ("aws_secret", "cloud", "HIGH",
     r"(?i)\baws_secret_access_key\b\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{20,})", 0.9, False),
    ("github_token", "cloud", "HIGH", r"\bgh[opsu]_[A-Za-z0-9]{10,}\b", 0.93, True),
    ("slack_token", "cloud", "HIGH", r"\bxox[bap]-[A-Za-z0-9-]{8,}\b", 0.93, True),
    ("google_oauth", "cloud", "HIGH", r"\bya29\.[A-Za-z0-9_-]{10,}\b", 0.9, True),
    ("groq_key", "api_key", "HIGH", r"\bgsk_[A-Za-z0-9]{10,}\b", 0.93, True),
    ("sk_key", "api_key", "HIGH", r"\bsk-(?!test\b)[A-Za-z0-9]{10,}\b", 0.9, True),
    ("bearer_token", "api_key", "HIGH",
     r"(?i)\bbearer\s+([A-Za-z0-9\-._~+/=]{12,})", 0.88, False),
    ("api_key_assign", "api_key", "HIGH",
     r"(?i)\b(api[_-]?key|apikey|access_token|auth_token|client_secret)\b\s*[:=]\s*['\"]?([^\s'\",;]{8,})",
     0.85, False),
    ("secret_assign", "api_key", "HIGH",
     r"(?i)\bsecret\b\s*[:=]\s*['\"]?([^\s'\",;]{8,})", 0.8, False),
    ("api_key_bare_value", "api_key", "HIGH",
     r"(?i)\bapi[_-]?key\b\s+((?:sk-|gsk-|ghp_|gho_|AKIA|xox[bap]-)[A-Za-z0-9\-_]{6,}[A-Za-z0-9\-_.=]*)",
     0.9, False),
    ("password_assign", "password", "HIGH",
     r"(?i)\b(passwd|password|pwd|contrase[ñn]a|clave(?: privada)?)\b\s*[:=]\s*['\"]?([^\s'\",;]{4,})", 0.85, False),
    ("user_pass_pair", "password", "CRITICAL",
     r"(?i)\b(user(name)?|login)\b\s*[:=]\s*['\"]?[^\s'\",;]+\s+(?:\S+\s+)?\b(passwd|password|pwd)\b\s*[:=]\s*['\"]?[^\s'\",;]{4,}",
     0.9, True),
    ("login_pair", "password", "CRITICAL",
     r"(?i)\buser\s*:\s*[^\s,;]+\s+password\s*:\s*[^\s,;]{4,}", 0.9, True),
]
