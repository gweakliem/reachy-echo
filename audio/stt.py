"""
Speech-to-text with a swappable backend.

Primary backend: Vosk (offline, ~50MB model, works on Pi 3B)
Fallback backend: faster-whisper (better accuracy, requires Pi 4+)

Usage:
    stt = SpeechToText(cfg["stt"])
    audio = stt.listen(timeout=8.0)   # returns raw audio bytes or None
    text = stt.transcribe(audio)      # returns transcribed string
"""

import json
import logging
import queue
import time
from typing import Optional

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class SpeechToText:
    def __init__(self, cfg: dict) -> None:
        self._backend = cfg.get("backend", "vosk")
        self._model_path = cfg["model_path"]
        self._sample_rate = cfg.get("sample_rate", 16000)
        self._silence_threshold_s = cfg.get("silence_threshold_s", 1.2)
        self._recognizer = None
        self._model = None
        self._load_backend()

    def _load_backend(self) -> None:
        if self._backend == "vosk":
            self._load_vosk()
        elif self._backend == "faster-whisper":
            self._load_faster_whisper()
        else:
            raise ValueError(f"Unknown STT backend: {self._backend}")

    def _load_vosk(self) -> None:
        from vosk import Model, KaldiRecognizer, SetLogLevel

        SetLogLevel(-1)
        log.info(f"Loading Vosk model from {self._model_path}")
        self._model = Model(self._model_path)
        self._recognizer = KaldiRecognizer(self._model, self._sample_rate)
        log.info("Vosk model loaded")

    def _load_faster_whisper(self) -> None:
        from faster_whisper import WhisperModel

        log.info("Loading Faster-Whisper tiny.en model")
        self._model = WhisperModel(
            "tiny.en",
            device="cpu",
            compute_type="int8",
        )
        log.info("Faster-Whisper model loaded")

    def listen(self, timeout: float = 8.0) -> Optional[bytes]:
        """
        Record audio from mic until silence is detected or timeout.
        Returns raw PCM bytes, or None on timeout with no speech.
        """
        log.debug(f"Listening (timeout={timeout}s)...")

        audio_queue: queue.Queue = queue.Queue()
        frames = []
        speech_started = False
        silence_start: Optional[float] = None
        start_time = time.time()

        def callback(indata, frame_count, time_info, status):
            audio_queue.put(bytes(indata))

        chunk_size = int(self._sample_rate * 0.1)  # 100ms chunks
        with sd.RawInputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=chunk_size,
            callback=callback,
        ):
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    log.debug("Listen timeout reached")
                    break

                try:
                    chunk = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                frames.append(chunk)

                # Simple energy-based VAD to detect speech/silence
                audio_np = np.frombuffer(chunk, dtype=np.int16)
                energy = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))

                if energy > 300:  # speech energy threshold
                    speech_started = True
                    silence_start = None
                elif speech_started:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > self._silence_threshold_s:
                        log.debug("Silence detected — end of utterance")
                        break

        if not speech_started or not frames:
            return None

        return b"".join(frames)

    def transcribe(self, audio: bytes) -> str:
        """Transcribe raw PCM bytes to text."""
        if self._backend == "vosk":
            return self._transcribe_vosk(audio)
        elif self._backend == "faster-whisper":
            return self._transcribe_faster_whisper(audio)
        return ""

    def _transcribe_vosk(self, audio: bytes) -> str:
        self._recognizer.AcceptWaveform(audio)
        result = json.loads(self._recognizer.FinalResult())
        text = result.get("text", "").strip()
        log.debug(f"Vosk transcription: '{text}'")
        return text

    def _transcribe_faster_whisper(self, audio: bytes) -> str:
        import io
        import wave

        # Faster-Whisper needs a WAV file or numpy array
        audio_np = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(audio_np, language="en")
        text = " ".join(seg.text.strip() for seg in segments).strip()
        log.debug(f"Faster-Whisper transcription: '{text}'")
        return text
