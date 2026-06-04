"""
Named robot expressions — maps semantic events to choreographed animations.

Each method orchestrates head + antenna + body movements to make
Reachy feel expressive and intentional in response to voice commands.
"""

import logging
import threading
import time

from .reachy_client import ReachyClient

log = logging.getLogger(__name__)


class Expressions:
    def __init__(self, robot: ReachyClient) -> None:
        self._robot = robot
        self._alarm_thread: threading.Thread | None = None
        self._alarm_running = False

    # ------------------------------------------------------------------
    # Wake word
    # ------------------------------------------------------------------

    def on_wake(self, doa_radians: float = 1.57) -> None:
        """
        Reachy hears its name — looks up attentively and turns toward speaker.
        """
        log.debug("Expression: wake")
        self._robot.look_toward_speaker(doa_radians)
        self._robot.look_up(duration=0.35)
        self._robot.antennas_perk()

    # ------------------------------------------------------------------
    # Timer commands
    # ------------------------------------------------------------------

    def on_timer_set(self) -> None:
        """Confirmation nod + happy antenna wiggle."""
        log.debug("Expression: timer_set")
        self._robot.nod()
        self._robot.antennas_happy()

    def on_timer_reset(self) -> None:
        """Quick nod + brief wiggle."""
        log.debug("Expression: timer_reset")
        self._robot.nod()
        self._robot.antennas_happy()

    def on_timer_stopped(self) -> None:
        """Slow nod down + antenna droop then recover."""
        log.debug("Expression: timer_stopped")
        self._robot.nod()
        self._robot.antennas_droop()
        time.sleep(0.4)
        self._robot.antennas_neutral()

    # ------------------------------------------------------------------
    # Alarm
    # ------------------------------------------------------------------

    def on_alarm(self) -> None:
        """
        Timer has fired — head shakes, antennas go frantic, body spins.
        Designed to run once per alarm cycle in ALARMING state.
        """
        log.debug("Expression: alarm")
        self._robot.shake_head()
        self._robot.antennas_frantic()
        self._robot.spin(degrees=180, duration=1.0)

    def on_alarm_dismissed(self) -> None:
        """Alarm was acknowledged — settle back to neutral."""
        log.debug("Expression: alarm_dismissed")
        self._robot.nod()
        self._robot.antennas_happy()
        time.sleep(0.3)
        self._robot.reset_pose()
        self._robot.antennas_neutral()
