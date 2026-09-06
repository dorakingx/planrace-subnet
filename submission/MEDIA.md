# Media status and provenance

## Submitted demo

`planrace-localnet-demo.mp4` is the 62-second silent recording of the public
evidence dashboard submitted to HackQuest. It shows localnet evidence and
limitations. It is not the final testnet-flow demonstration.

On 2026-09-07 JST, the uploaded HackQuest MP4 returned HTTP 200 without
authentication, had a stored length of 553,468 bytes, and decoded in full with
ffmpeg exit code 0. This verifies media delivery/decodability, not subjective
playback quality or the missing testnet scenes.

## Interim pitch

The editable source is `PlanRace_Checkpoint_Pitch.pptx`. Narration is in
`pitch-narration.json`. The assembly scripts use the existing rendered slides,
sentence-level audio and measured audio durations to create an MP4 with an
English subtitle track plus a sidecar SRT. Subtitle display depends on the
player; captions are not burned into the image.

Local synthesis uses [Kokoro-82M v1.0](https://huggingface.co/hexgrad/Kokoro-82M),
whose model card specifies Apache-2.0, with the standard `af_heart` synthetic
voice. This is not a recording of the project owner or a cloned person.
The script checks the model SHA-256 published in the model card before loading
it. The original slides and narration were prepared with Codex assistance.
No hosted speech API or paid media service is used.

Reproduction prerequisites: Ruby, ffmpeg/ffprobe, an isolated Python environment
containing `kokoro==0.9.4`, `soundfile`, and spaCy's `en_core_web_sm==3.8.0`
(install the language model explicitly into the same isolated environment),
and rendered PNGs of the exact deck
(SHA-256 `d95c48cf8cd2dcb202a7157b779c62211d11e5a7d31d000bd7e1599237ac0e50`)
under `.artifacts/pitch/rendered-v2/slide-1.png` through `slide-10.png`.
Those private intermediate images are not committed; render them from the
supplied deck before running these scripts on another machine.

```bash
UV_NO_CONFIG=true .artifacts/kokoro-venv/bin/python scripts/synthesize_pitch.py
ruby scripts/build_interim_pitch.rb
```

Do not overwrite an existing output or restart an active render without
inspecting its process and partial artifacts. A failed run stops with its
existing artifacts intact. Review them before choosing a fresh build directory.

The interim pitch explicitly discloses missing public testnet execution,
unproven production cost asymmetry and buyer demand, and the measured
behavior-replica allocation gain. It must not replace the final testnet demo.
Full perceptual listening and subtitle/player compatibility checks remain
separate from metadata and decode checks.

The generated candidate was saved to HackQuest's Pitch Video field on
2026-09-07 JST; the public page still reports the project as submitted.
The public asset returned HTTP 200, and its stored MD5 matches the local file.
It is 253.527 seconds, 6,239,270 bytes, 1920x1080 H.264 video with AAC audio
and an English `mov_text` subtitle track. Local and unauthenticated public-URL
full-file ffmpeg decoding both passed with exit code 0.
All 39 subtitle cues match the narration text after whitespace normalization.
Sidecar SRT and WebVTT captions are included. These technical checks do not
establish full perceptual quality or satisfaction of the testnet requirement.
The exact published URL and SHA-256 are in `HACKQUEST_SUBMISSION_RECEIPT.md`.

## Rejected public-audio source

A private timing rehearsal used macOS Samantha. It is retained only in the
ignored `.artifacts` directory and must not be uploaded or committed.
[Apple's macOS Sequoia license, section 2F](https://www.apple.com/legal/sla/docs/macOSSequoia.pdf)
restricts System Voices to personal, non-commercial uses and excludes public
sharing. The public candidate therefore uses the separately licensed Kokoro
model instead. The submitted silent dashboard demo contains no System Voice.
