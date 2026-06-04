# reachy-echo

A voice assistant for the Reachy Mini Lite robot that replaces Amazon Echo Dot functions. Built to run on a Raspberry Pi (targeting Pi 3B initially, upgrade path to Pi 4/5), connected to the robot via USB-C.

## Goal

Replace core Echo Dot functions with Reachy Mini as the physical interface. The robot listens for a wake word, interprets voice commands, executes skills, and responds with both speech and expressive physical animations.

## Hardware

- **Robot**: Reachy Mini Lite (pollen-robotics/reachy_mini SDK)
  - Connected to Raspberry Pi via USB-C
  - 2 microphones with Direction of Arrival (DoA) detection
  - 5W speaker
  - 6-DoF head, moveable antennas, 360° body yaw
  - No onboard compute — Pi is the brain
- **Compute**: Raspberry Pi 3B (upgrade to Pi 4 or 5 planned)
  - Always-on, headless Linux
  - USB-C to Reachy Mini Lite
- **Target OS**: Raspberry Pi OS (64-bit Bookworm) or Ubuntu 22.04

## Architecture

```
Reachy Mini Lite (mic/speaker/motors)
        |  USB-C
Raspberry Pi
  ├── wake_word.py     — openWakeWord, runs continuously, very lightweight
  ├── stt.py           — Vosk small-en model, ~50MB, streaming API
  ├── skills/          — intent routing + skill execution
  ├── tts.py           — Piper TTS low-quality voice (Pi 3B) or medium (Pi 4+)
  └── expressions.py   — named robot animations mapped to events
```

All processing is local/offline. Cloud API fallbacks are stubbed but disabled by default.

## Tech Stack

| Component | Library | Notes |
|---|---|---|
| Wake word | openWakeWord | Uses pre-trained "Reachy" ONNX model |
| STT | Vosk (vosk-model-small-en-us) | Streaming, ~50MB model |
| Intent | regex + fuzzy matching | No LLM needed for constrained skill set |
| TTS | Piper TTS | `en_US-amy-low` on Pi 3B, `en_US-amy-medium` on Pi 4+ |
| Robot SDK | reachy_mini | pip install reachy-mini |
| Service | systemd | Auto-start on boot, auto-restart on crash |

## Skills Implemented

### TimerSkill
- **Set timer**: "set a timer for 5 minutes", "timer for 30 seconds", "remind me in 10 minutes", etc.
- **Reset timer**: "reset timer", "restart the timer", "start over"
- **Stop timer**: "stop timer", "cancel timer", "dismiss"
- When alarm fires: plays repeating sound + robot expressive animation until dismissed

## Physical Reactions (expressions.py)

| Event | Head | Antennas | Body | Sound |
|---|---|---|---|---|
| Wake word | looks up | quick perk | turns toward speaker (DoA) | soft chime |
| Timer set | nod | happy wiggle | — | TTS confirmation |
| Timer reset | nod | quick wiggle | — | TTS confirmation |
| Timer stopped | slow nod down | droop then recover | — | TTS confirmation |
| Timer firing | shakes side to side | frantic wiggle | spins | repeating alarm |
| Alarm dismissed | nod | satisfied settle | — | "Okay!" |

## File Structure

```
reachy-echo/
├── CLAUDE.md                  ← you are here
├── README.md
├── config.yaml                ← all tuneable settings
├── requirements.txt
├── main.py                    ← main event loop / state machine
│
├── audio/
│   ├── __init__.py
│   ├── wake_word.py           ← openWakeWord listener thread
│   ├── stt.py                 ← Vosk STT wrapper (swappable backend)
│   └── tts.py                 ← Piper TTS wrapper (swappable backend)
│
├── skills/
│   ├── __init__.py
│   ├── base.py                ← Skill ABC: match(text) + execute(text, robot)
│   ├── registry.py            ← routes parsed intent to correct skill
│   └── timer.py               ← TimerSkill implementation
│
├── robot/
│   ├── __init__.py
│   ├── reachy_client.py       ← thin wrapper around reachy_mini SDK
│   └── expressions.py         ← named animations: wake, nod, happy, alarm, etc.
│
├── models/                    ← downloaded model files (gitignored)
│   ├── wake_word/             ← openWakeWord .onnx model for "Reachy"
│   ├── stt/                   ← Vosk model directory
│   └── tts/                   ← Piper .onnx + .onnx.json files
│
└── systemd/
    └── reachy-echo.service    ← systemd unit for auto-start on Pi
```

## State Machine (main.py)

```
IDLE → [wake word detected] → LISTENING → [silence/timeout] → PROCESSING
PROCESSING → [intent matched] → EXECUTING → IDLE
PROCESSING → [no match] → IDLE (with "sorry" response)
EXECUTING (timer running) → [timer fires] → ALARMING
ALARMING → [stop command] → IDLE
```

## Configuration (config.yaml)

Key settings to tune per hardware:
- `wake_word.threshold` — detection sensitivity (default 0.5)
- `stt.model_path` — path to Vosk model
- `tts.voice` — Piper voice name
- `tts.quality` — `low` for Pi 3B, `medium` for Pi 4+
- `robot.enabled` — set false for dev/testing without hardware

## Development Notes

- Run `python main.py --no-robot` to test audio pipeline without Reachy connected
- Run `python main.py --no-audio` to test robot expressions without microphone
- Run `python main.py --sim` to use Reachy MuJoCo simulator instead of real hardware
- All audio backends implement the same interface — swap by changing config.yaml
- The `Skill.match()` method returns a confidence float (0.0–1.0); registry picks highest

## Tech Stack (build tooling)

| Tool | Purpose |
|---|---|
| uv | Virtualenv + package management (`uv sync`, `uv run`) |
| pyproject.toml | Single source of truth for deps |
| uv.lock | Lockfile — commit this |

Optional extras: `uv sync --extra whisper` (Pi 4+ STT), `uv sync --extra cloud` (cloud backends).

## Model Setup (run once on Pi)

```bash
# Wake word model (pre-trained "Reachy" model by andyjmorgan)
# Download from: https://github.com/andyjmorgan/reachy-wake-word
# Place .onnx file in models/wake_word/

# Vosk STT model
cd models/stt
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip

# Piper TTS voice
cd models/tts
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx.json
```

## Upgrade Path

When moving from Pi 3B → Pi 4/5:
1. In `config.yaml`: change `tts.quality` from `low` to `medium`
2. Download the medium Piper voice model
3. Optionally switch `stt.backend` from `vosk` to `faster-whisper` for better accuracy

## Known Constraints (Pi 3B)

- Vosk STT: ~2–4 second latency for short commands (acceptable)
- Piper TTS: use `low` quality only; `medium` is too slow
- Do not run both STT and TTS simultaneously — sequence them
- Wake word detection runs in a separate thread and is always-on lightweight
