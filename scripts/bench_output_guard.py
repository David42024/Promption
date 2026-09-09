"""Benchmark sintético del Output Guard (valores 100% ficticios FAKE_*).

Uso:
    python scripts/bench_output_guard.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.output_guard import guard_response  # noqa: E402

JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
       "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
PK = ("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0FAKEFAKEKEY\n"
      "-----END PRIVATE KEY-----")

# (categoria, texto, debe_bloquear_o_redactar)
CASES = [
    ("API keys", "usa api_key=FAKE_API_KEY_9f8e7d6c5b4a en prod", True),
    ("API keys", "Authorization: Bearer FAKE_TOKEN_abc123XYZ789", True),
    ("API keys", "api_key = FAKE_API_KEY_1234567890 del servicio", True),
    ("API keys", "La clave es FAKE_API_KEY_Qq99887766, guardala", True),
    ("API keys", "client_secret=FAKE_SECRET_s3cr3t9x7q2w", True),
    ("Passwords", "login: deploy password: FAKE_PW_deploy99!", True),
    ("Passwords", "user: admin password: FAKE_PW_qwerty99", True),
    ("Passwords", "passwd=FAKE_PW_root0077 del contenedor", True),
    ("Passwords", "contraseña=FAKE_CLAVE_12345678 del servicio", True),
    ("Tokens", "auth_token=FAKE_AUTH_abcDEF123456", True),
    ("Tokens", "access_token=FAKE_ACC_z9y8x7w6v5", True),
    ("JWT", f"tu sesion: {JWT} usala rapido", True),
    ("JWT", f"header.payload: {JWT}", True),
    ("Private keys", f"llave:\n{PK}", True),
    ("Private keys", "-----BEGIN RSA PRIVATE KEY-----\nMIIEowFAKEFAKE\n-----END RSA PRIVATE KEY-----", True),
    ("Connection strings", "postgresql://svc:FAKE_PW_9x8@db.internal:5432/app", True),
    ("Connection strings", "mongodb+srv://api:FAKE_PW_mongo1@cluster0/x", True),
    ("Connection strings", "mysql://root:FAKE_PW_sql42@localhost/shop", True),
    ("Benign security prose", "Una API key permite autenticar una aplicación.", False),
    ("Benign security prose", "Debes almacenar las contraseñas utilizando hashing.", False),
    ("Benign security prose", "Un JWT contiene tres partes separadas por puntos.", False),
    ("Benign security prose", "¿Qué diferencia existe entre un token y una sesión?", False),
    ("Benign security prose", "Nunca compartas tu clave privada con nadie.", False),
    ("Benign security prose", "Guía: usa gestores de claves y 2FA.", False),
    ("Code placeholders", "Pon API_KEY=<YOUR_API_KEY> en tu .env de ejemplo.", False),
    ("Code placeholders", "Usa PASSWORD=${PASSWORD} en el tutorial.", False),
    ("Code placeholders", 'Lee con os.getenv("API_KEY") sin valor real.', False),
    ("Code placeholders", "process.env.API_KEY // configurado en el servidor", False),
    ("Code placeholders", "api_key=changeme antes de desplegar", False),
    ("Code placeholders", "password: test // credencial de ejemplo", False),
]


def main() -> None:
    tp = tn = fp = fn = 0
    cats: dict[str, list[int]] = {}
    for cat, text, bad in CASES:
        blocked = guard_response(text).action in ("BLOCK", "REDACT")
        ok = blocked == bad
        c = cats.setdefault(cat, [0, 0])
        c[1] += 1
        c[0] += ok
        if bad and blocked:
            tp += 1
        elif not bad and not blocked:
            tn += 1
        elif not bad:
            fp += 1
            print(f"  FP [{cat}] {text[:70]}")
        else:
            fn += 1
            print(f"  FN [{cat}] {text[:70]}")
        if not ok and bad:
            print(f"  MISS [{cat}] {text[:70]}")
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn) if tp + fn else 0
    print(f"TP={tp} TN={tn} FP={fp} FN={fn} P={p:.3f} R={r:.3f} "
          f"F1={(2*p*r/(p+r) if p+r else 0):.3f} FPR={fp/(fp+tn):.3f} FNR={fn/(fn+tp):.3f}")
    for cat, (ok, tot) in cats.items():
        print(f"  {cat}: {ok}/{tot}")


if __name__ == "__main__":
    main()
