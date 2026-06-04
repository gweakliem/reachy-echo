"""
Wake word detection using openWakeWord.

Runs in a background thread, continuously processing audio from
Reachy Mini's microphones. Signals main loop when "Reachy" is detected.
"""

import logging
import threading
import time
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


class WakeWordDetector:
    """
    Listens continuously for the wake word using openWakeWord.

    Uses the pre-trained "Reachy" ONNX model from:
    https://github.com/andyjmorgan/reachy-wake-word

    Audio is pulled from Reachy Mini's mic array via sounddevice,
    falling back to the system default mic if Reachy is not connected.
    """

    def __init__(self, cfg: dict) -> None:
        self._model_path = cfg["model_path"]
        self._threshold = cfg.get("threshold", 0.5)
        self._sample_rate = cfg.get("sample_rate", 16000)
        self._chunk_ms = cfg.get("chunk_ms", 80)
        self._chunk_size = int(self._sample_rate * self._chunk_ms / 1000)

        self._detected = threading.Event()
        self._last_doa: float = 0.0
        self._running = False
        self._suspended = False
        self._thread: Optional[threading.Thread] = None
        self._model = None

    def _load_model(self) -> None:
        import openwakeword
        import openwakeword.utils
        from openwakeword.model import Model
        from pathlib import Path

        # melspectrogram.onnx is not bundled in the pip wheel — download on first run
        resources = Path(openwakeword.__file__).parent / "resources" / "models"
        if not (resources / "melspectrogram.onnx").exists():
            log.info("Downloading openWakeWord bundled models (first run)...")
            openwakeword.utils.download_models()

        log.info(f"Loading wake word model: {self._model_path}")
        self._model = Model(
            wakeword_models=[self._model_path],
            inference_framework="onnx",
        )
        log.info("Wake word model loaded")

    def start(self) -> None:
        """Start background detection thread."""
        try:
            self._load_model()
        except Exception as e:
            log.warning(f"Wake word model unavailable: {e}")
            log.warning("Running without wake word detection — use --text to send commands")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Wake word detector started")

    def suspend(self) -> None:
        """Release the audio device so STT can open its own stream."""
        self._suspended = True

    def resume(self) -> None:
        """Reclaim the audio device after STT is done."""
        self._suspended = False

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        import sounddevice as sd
        import time

        log.debug("Wake word detection thread running")
        while self._running:
            if self._suspended:
                time.sleep(0.05)
                continue
            try:
                with sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self._chunk_size,
                ) as stream:
                    while self._running and not self._suspended:
                        audio_chunk, _ = stream.read(self._chunk_size)
                        audio_np = np.frombuffer(audio_chunk, dtype=np.int16)

                        prediction = self._model.predict(audio_np)
                        model_name = list(prediction.keys())[0]
                        score = prediction[model_name]

                        if score >= self._threshold:
                            log.debug(f"Wake word score: {score:.3f} >= {self._threshold}")
                            self._detected.set()
            except Exception as e:
                if self._running and not self._suspended:
                    log.warning(f"Wake word stream error: {e}")
                time.sleep(0.1)

    def wait_for_wake_word(self) -> float:
        """Block until wake word is detected. Returns DoA angle in radians."""
        self._detected.clear()
        self._detected.wait()
        self._detected.clear()
        return self._last_doa

    def detected(self) -> bool:
        """Non-blocking check — returns True once then resets."""
        if self._detected.is_set():
            self._detected.clear()
            return True
        return False

    def last_doa(self) -> float:
        return self._last_doa

    def set_doa(self, doa: float) -> None:
        """Called by ReachyClient when DoA updates."""
        self._last_doa = doa
