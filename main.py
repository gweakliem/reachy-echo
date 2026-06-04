"""
reachy-echo: main event loop

State machine:
  IDLE -> LISTENING -> PROCESSING -> EXECUTING -> IDLE
                                               -> ALARMING -> IDLE
"""

import argparse
import logging
import os
import sys
import time
from enum import Enum, auto
from pathlib import Path

import yaml

from audio.wake_word import WakeWordDetector
from audio.stt import SpeechToText
from audio.tts import TextToSpeech
from robot.reachy_client import ReachyClient
from robot.expressions import Expressions
from skills.registry import SkillRegistry


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    EXECUTING = auto()
    ALARMING = auto()


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def setup_logging(cfg: dict) -> None:
    level = getattr(logging, cfg.get("level", "INFO").upper())
    log_file = cfg.get("file")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            *([] if not log_file else [logging.FileHandler(log_file)]),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reachy Echo voice assistant")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--no-robot", action="store_true", help="Run without Reachy hardware"
    )
    parser.add_argument(
        "--no-audio", action="store_true", help="Disable microphone input (test mode)"
    )
    parser.add_argument(
        "--sim", action="store_true", help="Use Reachy MuJoCo simulator"
    )
    parser.add_argument(
        "--text", metavar="CMD", help="Skip wake word and process a single text command"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    setup_logging(cfg["logging"])
    log = logging.getLogger("main")

    log.info("Starting reachy-echo")

    # Override config from CLI flags
    if args.no_robot:
        cfg["robot"]["enabled"] = False
    if args.sim:
        cfg["robot"]["connection_mode"] = "sim"

    # Initialise components
    robot = ReachyClient(cfg["robot"])
    expressions = Expressions(robot)
    tts = TextToSpeech(cfg["tts"])
    stt = SpeechToText(cfg["stt"])
    wake = WakeWordDetector(cfg["wake_word"])
    registry = SkillRegistry(robot=robot, expressions=expressions, tts=tts)

    state = State.IDLE
    active_skill = None

    # One-shot text mode (useful for testing without mic)
    if args.text:
        log.info(f"One-shot mode: '{args.text}'")
        skill, response = registry.handle(args.text)
        if response:
            tts.speak(response)
        return

    log.info("Entering main loop — say 'Reachy' to activate")

    try:
        wake.start()
        while True:
            if state == State.IDLE:
                # Block until wake word fires
                doa = wake.wait_for_wake_word()
                log.info(f"Wake word detected (DoA={doa:.2f} rad)")
                expressions.on_wake(doa)
                tts.play_chime()
                state = State.LISTENING

            elif state == State.LISTENING:
                log.info("Listening for command...")
                wake.suspend()
                audio = stt.listen(timeout=cfg["stt"]["listen_timeout_s"])
                wake.resume()
                if audio is None:
                    log.info("Listen timeout — returning to idle")
                    state = State.IDLE
                    continue
                state = State.PROCESSING

            elif state == State.PROCESSING:
                text = stt.transcribe(audio)
                log.info(f"Transcribed: '{text}'")
                if not text:
                    tts.speak("Sorry, I didn't catch that.")
                    state = State.IDLE
                    continue

                skill, response = registry.handle(text)
                if skill is None:
                    tts.speak("Sorry, I'm not sure how to help with that.")
                    state = State.IDLE
                    continue

                active_skill = skill
                tts.speak(response)
                state = State.EXECUTING

            elif state == State.EXECUTING:
                # Poll active skill — it signals when it needs attention
                # (e.g. timer fires)
                event = active_skill.poll()
                if event == "alarm":
                    state = State.ALARMING
                elif event == "done":
                    active_skill = None
                    state = State.IDLE
                else:
                    # While executing, still listen for commands (stop, reset)
                    if wake.detected():
                        doa = wake.last_doa()
                        expressions.on_wake(doa)
                        tts.play_chime()
                        wake.suspend()
                        audio = stt.listen(timeout=cfg["stt"]["listen_timeout_s"])
                        wake.resume()
                        if audio:
                            text = stt.transcribe(audio)
                            log.info(f"In-flight command: '{text}'")
                            skill, response = registry.handle(text, active_skill)
                            if skill:
                                active_skill = skill
                                tts.speak(response)
                    time.sleep(0.1)

            elif state == State.ALARMING:
                log.info("Alarm firing!")
                expressions.on_alarm()
                tts.play_alarm()

                # Listen for dismissal without requiring wake word
                wake.suspend()
                audio = stt.listen(timeout=5.0)
                wake.resume()
                if audio:
                    text = stt.transcribe(audio)
                    log.info(f"Alarm response: '{text}'")
                    if active_skill and active_skill.is_dismiss_command(text):
                        expressions.on_alarm_dismissed()
                        tts.speak("Okay!")
                        active_skill.stop()
                        active_skill = None
                        state = State.IDLE
                # If no response, loop back and fire alarm again

    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        wake.stop()
        robot.disconnect()


if __name__ == "__main__":
    main()
