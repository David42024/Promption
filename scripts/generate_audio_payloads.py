"""Generate audio test payloads (WAV) from the raw corpus.

Speech-to-text payloads: each prompt is read aloud using the Windows SAPI TTS
engine (built-in, no external binaries) and saved as a WAV file. The filter can
then be validated over transcriptions (``scripts/run_benchmark.py --audio-dir``).

Windows-only (requires PowerShell + System.Speech). Usage:
    python scripts/generate_audio_payloads.py [--samples-per-class 40] [--out data/audio_payloads]
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.training.dataset import load_raw_data  # noqa: E402
from src.utils.config import load_config  # noqa: E402
from src.utils.logger import logger  # noqa: E402

_CONF = load_config()

PS_TEMPLATE = r"""
param([string]$InFile, [string]$OutFile)
Add-Type -AssemblyName System.Speech
$txt = Get-Content -Raw -Encoding UTF8 $InFile
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo } | Where-Object { $_.Culture.Name -like 'en-*' } | Select-Object -First 1
if ($voice) { $synth.SelectVoice($voice.Name) }
$synth.SetOutputToWaveFile($OutFile)
$synth.Speak($txt)
$synth.Dispose()
"""


def speak(text: str, out_wav: Path, ps1: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        in_txt = Path(tmp) / "input.txt"
        in_txt.write_text(text, encoding="utf-8")
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(ps1), "-InFile", str(in_txt), "-OutFile", str(out_wav)],
            check=True, capture_output=True, text=True, timeout=120,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-per-class", type=int, default=40,
                        help="Audios por clase (maliciosos / benignos), si hay suficientes")
    parser.add_argument("--out", type=Path, default=Path(_CONF["paths"].get("audio_payloads", "data/audio_payloads")))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if os.name != "nt":
        raise RuntimeError("La generación de audio usa el TTS SAPI de Windows.")

    with tempfile.TemporaryDirectory() as tmp:
        ps1 = Path(tmp) / "speak.ps1"
        ps1.write_text(PS_TEMPLATE, encoding="utf-8")

        df = load_raw_data()
        out = args.out
        out.mkdir(parents=True, exist_ok=True)

        rows = []
        for label in (1, 0):
            sub = df[df["label"] == label]
            sub = sub.sample(n=min(args.samples_per_class, len(sub)), random_state=args.seed)
            prefix = "mal" if label == 1 else "ben"
            for i, (_, src) in enumerate(sub.reset_index(drop=True).iterrows()):
                fname = f"{prefix}_{i:03d}.wav"
                speak(src["prompt"], out / fname, ps1)
                rows.append({
                    "file": fname,
                    "prompt": src["prompt"],
                    "label": int(src["label"]),
                    "dataset": src["dataset"],
                    "attack_type": src["attack_type"],
                    "source": src["source"],
                })

    meta_path = out / "metadata.csv"
    pd.DataFrame(rows).to_csv(meta_path, index=False, encoding="utf-8")
    counts = {0: sum(r["label"] == 0 for r in rows), 1: sum(r["label"] == 1 for r in rows)}
    logger.info("Audios generados: %d maliciosos / %d benignos -> %s", counts[1], counts[0], out)
    logger.info("Metadatos: %s", meta_path)


if __name__ == "__main__":
    main()