"""Traducción masiva EN->ES con la API de Gemini (REST, sin dependencias nuevas).

Lee CSVs por lotes, traduce cada lote en UNA llamada (textos numerados,
respuesta JSON) y escribe un CSV con las filas traducidas.

Uso:
    set GEMINI_API_KEY=gsk...   # PowerShell: $env:GEMINI_API_KEY="..."
    python scripts/translate_batch.py --input data/raw/malicious_prompts.csv \\
        --out data/raw/malicious_translated_es.csv --limit 50
    python scripts/translate_batch.py --input data/raw/benign_prompts.csv \\
        --out data/raw/benign_translated_es.csv --limit 50 --skip-existing

Revisable en vivo: cada lote imprime EN->ES de muestra por consola.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.logger import logger  # noqa: E402

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            key = os.environ.get("GEMINI_API_KEY", "").strip()
        except Exception:  # noqa: BLE001
            pass
    if not key:
        raise SystemExit("Falta GEMINI_API_KEY (variable de entorno o .env)")
    return key


def build_prompt(texts: list[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    return (
        "Traduce cada texto del inglés al español neutro. "
        "Responde SOLO con un array JSON de strings, en el mismo orden, sin explicaciones.\n"
        f"{numbered}"
    )


def parse_response(data: dict, n: int) -> list[str]:
    """Extrae las n traducciones; tolera JSON con ruido o líneas numeradas."""
    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return []
    try:
        start, end = raw.index("["), raw.rindex("]")
        items = json.loads(raw[start:end + 1])
        if isinstance(items, list) and len(items) == n:
            return [str(x) for x in items]
    except (ValueError, json.JSONDecodeError):
        pass
    out, lines = [], raw.strip().splitlines()
    for line in lines:
        line = line.strip().lstrip("0123456789. )(-")
        if line:
            out.append(line)
    return out[:n] if len(out) == n else []


def _call_gemini(payload: dict, key: str, model: str) -> requests.Response:
    return requests.post(GEMINI_URL.format(model=model), params={"key": key},
                         json=payload, timeout=120)


def _payload(texts: list[str]) -> dict:
    return {
        "contents": [{"parts": [{"text": build_prompt(texts)}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }


def translate_batch(texts: list[str], key: str, model: str, retries: int = 5) -> list[str]:
    for attempt in range(retries):
        r = _call_gemini(_payload(texts), key, model)
        if r.status_code == 200:
            parsed = parse_response(r.json(), len(texts))
            if parsed:
                return parsed
            logger.warning("Lote no parseable (posible bloqueo de seguridad): fallback 1x1")
            return _translate_singles(texts, key, model)
        if r.status_code in (429, 503):
            wait = 30 * (attempt + 1)
            logger.warning("Gemini %s, esperando %ss", r.status_code, wait)
            time.sleep(wait)
            continue
        logger.warning("Gemini %s: %s", r.status_code, r.text[:200])
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"El lote no se tradujo tras {retries} intentos")


def _translate_singles(texts: list[str], key: str, model: str) -> list[str]:
    """Fallback: traduce de a uno; lo bloqueado por seguridad queda vacío y se filtra."""
    out = []
    for t in texts:
        try:
            r = _call_gemini(_payload([t]), key, model)
            parsed = parse_response(r.json(), 1) if r.status_code == 200 else []
            out.append(parsed[0] if parsed else "")
            if not parsed:
                logger.warning("Fila omitida (bloqueo o error): %r", t[:60])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fila omitida (%s): %r", exc, t[:60])
            out.append("")
        time.sleep(3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Traduce CSVs en lote EN->ES con Gemini")
    ap.add_argument("--input", required=True, help="CSV con columna prompt")
    ap.add_argument("--out", required=True, help="CSV destino de traducidas")
    ap.add_argument("--text-col", default="prompt")
    ap.add_argument("--batch-size", type=int, default=20, help="Textos por llamada")
    ap.add_argument("--limit", type=int, default=0, help="0 = todo")
    ap.add_argument("--source", default="translated_es")
    ap.add_argument("--model", default="gemini-3.6-flash")
    ap.add_argument("--skip-existing", action="store_true", help="Omite prompts ya traducidos")
    args = ap.parse_args()

    key = api_key()
    df = pd.read_csv(args.input, encoding="utf-8", encoding_errors="replace")
    if args.text_col not in df.columns:
        raise SystemExit(f"Columna '{args.text_col}' no existe en {args.input}")
    df = df[df[args.text_col].astype(str).str.strip().str.len() > 0]
    if args.limit:
        df = df.head(args.limit)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    recs: list[dict] = []
    if args.skip_existing and out.exists():
        old = pd.read_csv(out, encoding="utf-8", encoding_errors="replace")
        recs = old.to_dict("records")
    done: set[str] = {str(r.get(args.text_col, "")) for r in recs}
    todo = df[~df[args.text_col].astype(str).isin(done)].reset_index(drop=True)
    logger.info("%d filas a traducir (%d ya hechas)", len(todo), len(done))
    if todo.empty:
        print("Nada que traducir.")
        return

    def flush() -> None:
        pd.DataFrame(recs).drop_duplicates(args.text_col).to_csv(out, index=False, encoding="utf-8")

    groups = [todo.iloc[i:i + args.batch_size] for i in range(0, len(todo), args.batch_size)]
    for g in tqdm(groups, desc="Lotes"):
        texts = g[args.text_col].astype(str).tolist()
        trans = translate_batch(texts, key, args.model)
        for (_, row), t in zip(g.iterrows(), trans):
            t = (t or "").strip()
            if len(t) < 10:
                continue
            rec = row.to_dict()
            rec[args.text_col] = t
            rec["source"] = args.source
            recs.append(rec)
        print(f"  ej: {texts[0][:60]!r} -> {trans[0][:60]!r}", flush=True)
        flush()  # checkpoint por lote: un corte no pierde lo avanzado
        time.sleep(2)

    logger.info("%d traducidas -> %s", len(recs), out)


if __name__ == "__main__":
    main()
