# syntax=docker/dockerfile:1
# reachy-echo development container
#
# Uses linux/arm/v7 to closely match Raspberry Pi 3B (ARMv7).
# On Apple Silicon, Docker Desktop handles the emulation via Rosetta/QEMU.
#
# For Pi 4/5 compatibility instead, change to linux/arm64.
#
# Note: uv is used for local development (uv sync/run/lock).
# pip is used here because uv's resolver doesn't find ARMv7 wheels under QEMU emulation.

FROM --platform=linux/arm/v7 python:3.11-slim-bookworm

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Audio playback
    alsa-utils \
    libasound2-dev \
    portaudio19-dev \
    # Piper TTS runtime
    espeak-ng \
    # Vosk needs these
    libgomp1 \
    # numpy (piwheels build) links against OpenBLAS
    libopenblas0 \
    # Build tools (needed for psutil and other source-only packages on ARM v7)
    build-essential \
    # For pyusb / reachy-mini USB support (system libusb replaces libusb_package on Linux)
    libusb-1.0-0-dev \
    # Utilities
    wget \
    unzip \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create stub wheels for packages that have no ARM v7 Python 3.11 wheels anywhere.
#
# libusb_package: pyusb uses system libusb on Linux, so this stub is purely declarative.
# onnxruntime:    Microsoft dropped ARM32 cp311 wheels. Wake word detection (openwakeword)
#                 requires a real onnxruntime — install it natively on the Pi for production.
#                 In this dev container it installs but ONNX inference won't run.
RUN <<'EOF' python3
import zipfile, os
os.makedirs('/tmp/stubs', exist_ok=True)
stubs = [('libusb_package', '1.0.26.3'), ('onnxruntime', '1.10.0')]
for name, version in stubs:
    d = f'{name}-{version}.dist-info'
    with zipfile.ZipFile(f'/tmp/stubs/{name}-{version}-py3-none-any.whl', 'w') as w:
        w.writestr(f'{name}/__init__.py', '')
        w.writestr(f'{d}/METADATA', f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n')
        w.writestr(f'{d}/WHEEL', 'Wheel-Version: 1.0\nGenerator: stub\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
        w.writestr(f'{d}/RECORD', '')
EOF

RUN pip install --no-cache-dir --no-index --find-links /tmp/stubs \
    'libusb_package==1.0.26.3' \
    'onnxruntime==1.10.0'

# Install Python deps (layer-cached unless pyproject.toml changes)
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    --extra-index-url https://www.piwheels.org/simple/ \
    .

# Copy project source
COPY . .

# Create directories that are gitignored
RUN mkdir -p models/wake_word models/stt models/tts sounds logs

# Default: run with no real hardware (override in docker-compose or CLI)
CMD ["python", "main.py", "--no-robot"]
