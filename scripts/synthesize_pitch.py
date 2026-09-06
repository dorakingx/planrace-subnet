"""Local interim narration only; isolated media environment, no hosted TTS API."""

import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import spacy
from huggingface_hub import hf_hub_download
from kokoro import KPipeline

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".artifacts/pitch/kokoro-interim"
BUILD.mkdir(parents=True, exist_ok=True)
# Public model integrity digest, not a credential.
MODEL_SHA = (
    "496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4"  # pragma: allowlist secret
)
model = hf_hub_download("hexgrad/Kokoro-82M", "kokoro-v1_0.pth")
if hashlib.sha256(Path(model).read_bytes()).hexdigest() != MODEL_SHA:
    raise RuntimeError("Unexpected Kokoro model digest")
if not spacy.util.is_package("en_core_web_sm"):
    raise RuntimeError("Install en_core_web_sm explicitly in this isolated environment first")
pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device="cpu")
scenes = json.loads((ROOT / "submission/pitch-narration.json").read_text())
for scene in scenes:
    for index, sentence in enumerate(scene["sentences"]):
        output = BUILD / f"slide-{scene['slide']}-{index}.wav"
        if output.exists():
            raise RuntimeError(f"Existing output needs review before rerun: {output}")
        chunks = [audio.numpy() for _, _, audio in pipeline(sentence, voice="af_heart", speed=1)]
        if not chunks:
            raise RuntimeError("No audio generated")
        sf.write(output, np.concatenate(chunks), 24000, subtype="PCM_16")
        print(f"Synthesized slide {scene['slide']} sentence {index + 1}", flush=True)
