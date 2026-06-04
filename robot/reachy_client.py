"""
Thin wrapper around the reachy_mini SDK.

Handles connection lifecycle and provides a safe no-op fallback
when robot hardware is disabled (--no-robot flag or robot.enabled: false).

SDK docs: https://github.com/pollen-robotics/reachy_mini
"""

import logging
import math
from typing import Optional, Tuple

log = logging.getLogger(__name__)


class ReachyClient:
    def __init__(self, cfg: dict) -> None:
        self._enabled = cfg.get("enabled", True)
        self._connection_mode = cfg.get("connection_mode", "auto")
        self._turn_to_speaker = cfg.get("turn_to_speaker", True)
        self._animation_speed = cfg.get("animation_speed", 1.0)
        self._robot = None

        if self._enabled:
            self._connect()

    def _connect(self) -> None:
        try:
            from reachy_mini import ReachyMini

            kwargs = {}
            if self._connection_mode != "auto":
                kwargs["connection_mode"] = self._connection_mode

            log.info("Connecting to Reachy Mini...")
            self._robot = ReachyMini(**kwargs)
            self._robot.__enter__()
            log.info("Reachy Mini connected")
        except Exception as e:
            log.warning(f"Could not connect to Reachy Mini: {e}")
            log.warning("Running in no-robot mode")
            self._robot = None

    def disconnect(self) -> None:
        if self._robot is not None:
            try:
                self._robot.__exit__(None, None, None)
                log.info("Reachy Mini disconnected")
            except Exception as e:
                log.warning(f"Error disconnecting: {e}")

    @property
    def connected(self) -> bool:
        return self._robot is not None

    # ------------------------------------------------------------------
    # Head movement
    # ------------------------------------------------------------------

    def look_up(self, duration: float = 0.4) -> None:
        """Look up attentively (wake word response)."""
        self._goto_head(z=15, duration=duration)

    def nod(self) -> None:
        """Single affirmative nod."""
        self._goto_head(z=10, duration=0.25)
        self._goto_head(z=-5, duration=0.2)
        self._goto_head(z=0, duration=0.2)

    def shake_head(self) -> None:
        """Side-to-side shake (alarm firing)."""
        for _ in range(3):
            self._goto_head(y=15, duration=0.2)
            self._goto_head(y=-15, duration=0.2)
        self._goto_head(y=0, duration=0.2)

    def look_toward_speaker(self, doa_radians: float) -> None:
        """
        Rotate body yaw to face the direction of arrival.

        DoA: 0 = left, π/2 = front/back, π = right
        We convert to a body yaw angle.
        """
        if not self._turn_to_speaker or not self.connected:
            return
        # Convert DoA to degrees for body yaw
        # DoA of π/2 means speaker is directly in front — no rotation needed
        offset = math.degrees(doa_radians - math.pi / 2)
        self._goto_body_yaw(offset)

    def reset_pose(self, duration: float = 0.5) -> None:
        """Return head and body to neutral position."""
        self._goto_head(x=0, y=0, z=0, roll=0, duration=duration)

    # ------------------------------------------------------------------
    # Antennas
    # ------------------------------------------------------------------

    def antennas_perk(self) -> None:
        """Quick upward perk — attention."""
        self._antennas("perk")

    def antennas_happy(self) -> None:
        """Happy wiggle."""
        self._antennas("wiggle")

    def antennas_frantic(self) -> None:
        """Fast frantic wiggle — alarm state."""
        self._antennas("wiggle")

    def antennas_droop(self) -> None:
        """Sad droop."""
        self._antennas("sad")

    def antennas_neutral(self) -> None:
        """Reset to neutral."""
        self._antennas("neutral")

    # ------------------------------------------------------------------
    # Body rotation
    # ------------------------------------------------------------------

    def spin(self, degrees: float = 360, duration: float = 2.0) -> None:
        """Rotate body (alarm expression)."""
        self._goto_body_yaw(degrees, duration=duration)

    # ------------------------------------------------------------------
    # Internal SDK calls (all safe-guarded)
    # ------------------------------------------------------------------

    def _goto_head(
        self,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        roll: float = 0,
        duration: float = 0.4,
    ) -> None:
        if not self.connected:
            return
        try:
            from reachy_mini.utils import create_head_pose

            self._robot.goto_target(
                head=create_head_pose(x=x, y=y, z=z, roll=roll, degrees=True, mm=True),
                duration=duration / self._animation_speed,
            )
        except Exception as e:
            log.debug(f"Head movement error (non-fatal): {e}")

    def _goto_body_yaw(self, degrees: float, duration: float = 0.5) -> None:
        if not self.connected:
            return
        try:
            self._robot.goto_target(
                body_yaw=degrees,
                duration=duration / self._animation_speed,
            )
        except Exception as e:
            log.debug(f"Body yaw error (non-fatal): {e}")

    def _antennas(self, state: str) -> None:
        if not self.connected:
            return
        try:
            antennas = self._robot.antennas
            if state == "perk":
                antennas.wiggle()
            elif state == "wiggle":
                antennas.wiggle()
            elif state == "sad":
                antennas.sad()
            elif state == "neutral":
                antennas.neutral() if hasattr(antennas, "neutral") else None
        except Exception as e:
            log.debug(f"Antenna error (non-fatal): {e}")

    # ------------------------------------------------------------------
    # DoA audio
    # ------------------------------------------------------------------

    def get_doa(self) -> Tuple[float, bool]:
        """
        Returns (angle_radians, is_speech_detected).
        DoA: 0=left, π/2=front, π=right
        """
        if not self.connected:
            return (math.pi / 2, False)
        try:
            return self._robot.media.get_DoA()
        except Exception:
            return (math.pi / 2, False)
