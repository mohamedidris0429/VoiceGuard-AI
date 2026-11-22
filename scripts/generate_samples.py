"""Generate small sample recordings for manually testing VoiceGuard AI.

Creates:
  storage/samples/synthetic-tts.wav   - text-to-speech (Windows SAPI) when available
  storage/samples/voiced-tone.wav     - deterministic harmonic test signal

These are convenience fixtures for exercising the pipeline. The harmonic signal
is not human speech, so its verdict is not meaningful evidence of anything.

Usage:
    backend\\.venv\\Scripts\\python.exe scripts\\generate_samples.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "storage" / "samples"
SAMPLE_RATE = 16000


def voiced_tone(path: Path, seconds: float = 4.0) -> Path:
    rng = np.random.default_rng(11)
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    base = 130.0 + 8.0 * np.sin(2 * np.pi * 0.6 * t)
    signal = 0.3 * np.sin(2 * np.pi * base * t)
    signal += 0.14 * np.sin(2 * np.pi * 2 * base * t + 0.4)
    signal += 0.07 * np.sin(2 * np.pi * 3 * base * t + 0.9)
    signal += rng.normal(0, 0.003, t.size)
    envelope = 0.55 + 0.45 * np.sin(2 * np.pi * 1.4 * t) ** 2
    signal = signal * envelope
    signal = 0.9 * signal / max(1e-9, float(np.max(np.abs(signal))))
    sf.write(str(path), signal.astype(np.float32), SAMPLE_RATE, subtype="PCM_16")
    return path


def sapi_tts(path: Path, text: str) -> Path | None:
    """Use Windows System.Speech to synthesise speech (PowerShell 5.1)."""
    escaped_text = text.replace('"', "'")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f'$s.Speak("{escaped_text}"); '
        "$s.Dispose()"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  SAPI unavailable: {exc}")
        return None
    if result.returncode != 0 or not path.exists():
        print(f"  SAPI failed: {result.stderr.strip()[:200]}")
        return None
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    tone = voiced_tone(OUT / "voiced-tone.wav")
    print(f"created {tone.relative_to(ROOT)}")

    tts_path = OUT / "synthetic-tts.wav"
    tts = sapi_tts(
        tts_path,
        "Good afternoon. This is a synthetic voice sample used to test the VoiceGuard detection pipeline.",
    )
    if tts:
        print(f"created {tts.relative_to(ROOT)}")
    else:
        print("skipped text-to-speech sample (System.Speech unavailable)")

    print("\nRecord yourself saying a sentence, then upload both files to compare results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
