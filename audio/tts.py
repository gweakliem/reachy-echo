"""
Text-to-speech with a swappable backend.

Primary backend: Piper TTS (offline, ONNX, fast on Pi)
Fallback: Google TTS (cloud, higher quality)

Pre-generated audio clips are used for common short responses
(chime, alarm, "okay") to avoid TTS latency on hot paths.
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Directory for cached audio clips (chime, alarm sound, etc.)
SOUNDS_DIR = Path(__file__).parent.parent / "sounds"


class TextToSpeech:
    def __init__(self, cfg: dict) -> None:
        self._backend = cfg.get("backend", "piper")
        self._model_path = cfg.get("model_path", "models/tts/en_US-amy-low.onnx")
        self._sample_rate = cfg.get("sample_rate", 16000)
        self._use_cached = cfg.get("use_cached_responses", True)

        SOUNDS_DIR.mkdir(exist_ok=True)
        self._load_backend()

    def _load_backend(self) -> None:
        if self._backend == "piper":
            self._verify_piper()
        elif self._backend == "google":
            self._load_google()
        else:
            raise ValueError(f"Unknown TTS backend: {self._backend}")

    def _verify_piper(self) -> None:
        # Prefer the venv-local binary; fall back to whatever is on PATH
        import shutil
        venv_bin = Path(sys.executable).parent / "piper"
        self._piper_bin: Optional[str] = (
            str(venv_bin) if venv_bin.exists() else shutil.which("piper")
        )

        if not Path(self._model_path).exists():
            log.warning(
                f"Piper model not found at {self._model_path}. "
                "See CLAUDE.md 'Model Setup' section to download."
            )
        elif self._piper_bin:
            log.info(f"Piper TTS ready: {self._model_path}")
        else:
            log.warning("piper binary not found — TTS will be silent")

    def _load_google(self) -> None:
        from google.cloud import texttospeech

        self._google_client = texttospeech.TextToSpeechClient()
        log.info("Google TTS client initialised")

    def speak(self, text: str) -> None:
        """Synthesise and play text."""
        log.info(f"TTS: '{text}'")
        if self._backend == "piper":
            self._speak_piper(text)
        elif self._backend == "google":
            self._speak_google(text)

    def _speak_piper(self, text: str) -> None:
        """Run Piper CLI, capture raw PCM, play via sounddevice (cross-platform)."""
        if not Path(self._model_path).exists():
            log.error("Piper model missing — cannot speak")
            return
        if not self._piper_bin:
            log.error("piper binary not found — cannot speak")
            return

        import numpy as np
        import sounddevice as sd

        try:
            proc = subprocess.Popen(
                [self._piper_bin, "--model", self._model_path, "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            raw_audio, _ = proc.communicate(text.encode())
            if raw_audio:
                audio_np = np.frombuffer(raw_audio, dtype=np.int16)
                sd.play(audio_np, self._sample_rate)
                sd.wait()
        except Exception as e:
            log.error(f"Piper TTS error: {e}")

    def _speak_google(self, text: str) -> None:
        from google.cloud import texttospeech
        import io
        import sounddevice as sd
        import soundfile as sf

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=self._sample_rate,
        )
        response = self._google_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_data, _ = sf.read(io.BytesIO(response.audio_content), dtype="float32")
        sd.play(audio_data, self._sample_rate)
        sd.wait()

    def play_chime(self) -> None:
        """Play the wake-word activation chime."""
        chime_path = SOUNDS_DIR / "chime.wav"
        if chime_path.exists():
            self._play_wav(str(chime_path))
        else:
            log.debug("No chime.wav found in sounds/ — skipping")

    def play_alarm(self) -> None:
        """Play one cycle of the timer alarm sound."""
        alarm_path = SOUNDS_DIR / "alarm.wav"
        if alarm_path.exists():
            self._play_wav(str(alarm_path))
        else:
            # Fallback: synthesise a beep via TTS
            self.speak("Beep beep beep!")

    def _play_wav(self, path: str) -> None:
        import sounddevice as sd
        import soundfile as sf

        try:
            data, samplerate = sf.read(path, dtype="float32")
            sd.play(data, samplerate)
            sd.wait()
        except Exception as e:
            log.warning(f"Could not play {path}: {e}")
