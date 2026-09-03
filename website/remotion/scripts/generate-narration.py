#!/usr/bin/env python3
"""Generate the public GODFIN hero narration with a permissively licensed model."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel


MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
MODEL_REVISION = "85e237c12c027371202489a0ec509ded67b5e4b5"
SPEAKER = "Aiden"
NARRATION = (
    "Meet the real GODFIN desktop app with made-up data. "
    "Bring in Gmail transaction alerts or a supported bank statement. Review every row before it changes your month. "
    "Correct a category once, and GODFIN can remember that merchant next time. "
    "See regular payments, goals, and clear reports, while your money records stay on your computer."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        device_map="cuda:0",
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    waves, sample_rate = model.generate_custom_voice(
        text=NARRATION,
        language="English",
        speaker=SPEAKER,
        do_sample=False,
        max_new_tokens=4096,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, waves[0], sample_rate, subtype="PCM_16")
    payload = args.output.read_bytes()
    print(
        json.dumps(
            {
                "model": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "speaker": SPEAKER,
                "sample_rate": sample_rate,
                "samples": len(waves[0]),
                "duration_seconds": round(len(waves[0]) / sample_rate, 3),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
