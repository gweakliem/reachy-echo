# reachy-echo

A voice assistant for the [Reachy Mini Lite](https://github.com/pollen-robotics/reachy_mini) robot. Replaces Amazon Echo Dot functions — wake word, timers, and more — running fully offline on a Raspberry Pi.

## Hardware

- **Reachy Mini Lite** — connected to Pi via USB-C
- **Raspberry Pi 3B** (or newer) — always-on compute

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/yourname/reachy-echo
cd reachy-echo
uv sync
```

If you don't have uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 2. Download models

```bash
# Vosk STT model (~50MB)
mkdir -p models/stt && cd models/stt
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip && cd ../..

# Piper TTS voice
mkdir -p models/tts && cd models/tts
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx.json
cd ../..

# Wake word model — "Reachy" ONNX model by @andyjmorgan
# Download from: https://github.com/andyjmorgan/reachy-wake-word
# Place the .onnx file at: models/wake_word/reachy-wakeword.onnx
```

### 3. Linux udev rules (Pi only)

```bash
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="55d3", MODE="0666", GROUP="dialout" #Reachy Mini
SUBSYSTEM=="tty", ATTRS{idVendor}=="38fb", ATTRS{idProduct}=="1001", MODE="0666", GROUP="dialout" #Reachy Mini soundcard' \
  | sudo tee /etc/udev/rules.d/99-reachy-mini.rules
sudo udevadm control --reload && sudo udevadm trigger
sudo usermod -aG dialout $USER
```

### 4. Run

```bash
# Normal operation
python main.py

# Test without Reachy hardware
python main.py --no-robot

# Test a single command without mic
python main.py --text "set a timer for 5 minutes"

# Use MuJoCo simulator
python main.py --sim
```

## Usage

1. Say **"Reachy"** — the robot looks up and plays a chime
2. Say your command:
   - *"Set a timer for 5 minutes"*
   - *"Timer for 30 seconds"*
   - *"Remind me in 10 minutes"*
   - *"Reset timer"* / *"Restart the timer"*
   - *"Stop timer"* / *"Cancel timer"*
3. When the timer fires, say **"Stop"** or **"Okay"** to dismiss

## Auto-start on Pi

```bash
# Copy service file and enable
sudo cp systemd/reachy-echo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable reachy-echo
sudo systemctl start reachy-echo

# View logs
journalctl -u reachy-echo -f
```

## Configuration

Edit `config.yaml` to tune:
- Wake word sensitivity (`wake_word.threshold`)
- STT backend (`stt.backend: vosk` or `faster-whisper`)
- TTS voice quality (`tts.quality: low` for Pi 3B, `medium` for Pi 4+)
- Disable robot hardware (`robot.enabled: false`)

## Upgrade Path (Pi 3B → Pi 4/5)

1. Change `tts.quality: low` → `medium` in `config.yaml`
2. Download the medium Piper voice:
   ```bash
   cd models/tts
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
   ```
3. Update `tts.voice` and `tts.model_path` in `config.yaml`
4. Optionally switch `stt.backend: faster-whisper` for better accuracy

## Adding New Skills

1. Create `skills/your_skill.py` inheriting from `Skill`
2. Implement `match()`, `execute()`, `poll()`, `stop()`
3. Add to the registry in `skills/registry.py`

## Docker (Development on macOS)

Vosk has no macOS ARM wheels, so local development uses a container that emulates the Pi's ARMv7 environment.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with "Use Rosetta for x86/amd64 emulation" enabled

### Build and run

```bash
# Build the image (first time, ~2 min)
docker compose build dev

# Run with a test command — no hardware needed
docker compose run --rm dev python main.py --text "set a timer for 5 minutes"

# Interactive shell inside the container
docker compose run --rm dev bash

# Run the full assistant (no-robot mode, uses your Mac mic via portaudio)
docker compose run --rm dev
```

### Iterating

Source code is bind-mounted into the container, so edits on your Mac take effect immediately — no rebuild needed. Only `pyproject.toml` changes require a rebuild:

```bash
docker compose build dev
```

### On OSX

```
brew install espeak-ng
```

### On the Raspberry Pi

Copy the project to the Pi, then:

```bash
docker compose --profile pi up
```

Or run directly without Docker (native is faster on Pi):

```bash
uv sync
uv run python main.py
```
