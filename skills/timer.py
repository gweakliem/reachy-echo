"""
TimerSkill — set, reset, and stop a countdown timer.

Handles natural language variations:
  Set:   "set a timer for 5 minutes"
         "timer for 30 seconds"
         "set timer 10 minutes"
         "remind me in 2 minutes"
         "start a timer for an hour"
         "give me a 90 second timer"

  Reset: "reset timer" / "restart timer" / "start over" / "reset the timer"

  Stop:  "stop timer" / "cancel timer" / "dismiss" / "stop the timer"

  Dismiss alarm: "stop" / "okay" / "cancel" / "dismiss" / "yes"
"""

import logging
import re
import threading
import time
from typing import Optional

from .base import Skill

log = logging.getLogger(__name__)


# Patterns for setting a timer — all variations
_SET_PATTERNS = [
    # "set a timer for X minutes/seconds/hours"
    r"(?:set\s+(?:a\s+)?timer\s+(?:for\s+)?|timer\s+(?:for\s+)?|start\s+(?:a\s+)?timer\s+(?:for\s+)?|give\s+me\s+(?:a\s+)?)(?P<value>[\w\s]+?)\s*(?P<unit>second|seconds|minute|minutes|hour|hours|sec|secs|min|mins|hr|hrs)",
    # "remind me in X minutes"
    r"remind\s+me\s+in\s+(?P<value>[\w\s]+?)\s*(?P<unit>second|seconds|minute|minutes|hour|hours|sec|secs|min|mins|hr|hrs)",
    # "X minute timer"
    r"(?P<value>[\w\s]+?)\s*(?P<unit>second|seconds|minute|minutes|hour|hours|sec|secs|min|mins|hr|hrs)\s+timer",
]

_RESET_PATTERN = re.compile(
    r"\b(reset|restart|start\s+over|redo)\b.*\btimer\b"
    r"|\btimer\b.*\b(reset|restart)\b",
    re.IGNORECASE,
)

_STOP_PATTERN = re.compile(
    r"\b(stop|cancel|end|clear|delete)\b.*\btimer\b"
    r"|\btimer\b.*\b(stop|cancel)\b",
    re.IGNORECASE,
)

_DISMISS_PATTERN = re.compile(
    r"\b(stop|okay|ok|cancel|dismiss|yes|shut\s+up|enough)\b",
    re.IGNORECASE,
)

# Word-to-number mapping for spoken numbers
_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "ninety": 90, "a": 1, "an": 1,
}


def _parse_duration(value_str: str, unit_str: str) -> Optional[int]:
    """Parse a value+unit pair into seconds. Returns None if unparseable."""
    value_str = value_str.strip().lower()
    unit_str = unit_str.strip().lower()

    # Try numeric first
    try:
        value = float(value_str)
    except ValueError:
        # Try word numbers (handles "five", "twenty", "thirty seconds")
        total = 0
        for word in value_str.split():
            total += _WORD_NUMBERS.get(word, 0)
        value = total if total > 0 else None

    if value is None or value <= 0:
        return None

    value = int(value)

    if unit_str in ("second", "seconds", "sec", "secs"):
        return value
    elif unit_str in ("minute", "minutes", "min", "mins"):
        return value * 60
    elif unit_str in ("hour", "hours", "hr", "hrs"):
        return value * 3600

    return None


def _format_duration(seconds: int) -> str:
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        result = f"{mins} minute{'s' if mins != 1 else ''}"
        if secs:
            result += f" and {secs} second{'s' if secs != 1 else ''}"
        return result
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        result = f"{hours} hour{'s' if hours != 1 else ''}"
        if mins:
            result += f" and {mins} minute{'s' if mins != 1 else ''}"
        return result


class TimerSkill(Skill):
    """Manages a single countdown timer."""

    priority = 10

    def __init__(self) -> None:
        self._duration_s: Optional[int] = None
        self._end_time: Optional[float] = None
        self._fired: bool = False
        self._stopped: bool = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Skill interface
    # ------------------------------------------------------------------

    def match(self, text: str) -> float:
        text_lower = text.lower()

        # High confidence: explicit timer commands
        if _STOP_PATTERN.search(text_lower):
            return 0.95
        if _RESET_PATTERN.search(text_lower):
            return 0.95
        for pattern in _SET_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return 0.95

        # Medium confidence: mentions "timer" without clear action
        if "timer" in text_lower:
            return 0.6

        # Low confidence: time-related words
        if any(w in text_lower for w in ("remind", "minutes", "seconds", "alarm")):
            return 0.3

        return 0.0

    def execute(self, text: str) -> str:
        text_lower = text.lower()

        # Stop/cancel
        if _STOP_PATTERN.search(text_lower):
            return self._cmd_stop()

        # Reset/restart
        if _RESET_PATTERN.search(text_lower):
            return self._cmd_reset()

        # Try to set a new timer
        duration = self._parse_set_command(text_lower)
        if duration is not None:
            return self._cmd_set(duration)

        return "I'm not sure what to do with the timer. Try saying 'set a timer for 5 minutes'."

    def poll(self) -> Optional[str]:
        with self._lock:
            if self._stopped:
                return "done"
            if self._fired:
                return "alarm"
            if self._end_time is not None and time.time() >= self._end_time:
                self._fired = True
                log.info("Timer fired!")
                return "alarm"
        return None

    def is_dismiss_command(self, text: str) -> bool:
        return bool(_DISMISS_PATTERN.search(text))

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._end_time = None
            self._fired = False
        log.info("Timer stopped")

    # ------------------------------------------------------------------
    # Internal commands
    # ------------------------------------------------------------------

    def _cmd_set(self, duration_s: int) -> str:
        with self._lock:
            self._duration_s = duration_s
            self._end_time = time.time() + duration_s
            self._fired = False
            self._stopped = False
        label = _format_duration(duration_s)
        log.info(f"Timer set for {duration_s}s ({label})")
        return f"Timer set for {label}."

    def _cmd_reset(self) -> str:
        with self._lock:
            if self._duration_s is None:
                return "There's no timer to reset."
            self._end_time = time.time() + self._duration_s
            self._fired = False
            self._stopped = False
        label = _format_duration(self._duration_s)
        log.info(f"Timer reset to {self._duration_s}s")
        return f"Timer restarted for {label}."

    def _cmd_stop(self) -> str:
        with self._lock:
            had_timer = self._end_time is not None or self._fired
            self._end_time = None
            self._fired = False
            self._stopped = True
        if had_timer:
            log.info("Timer cancelled by user")
            return "Timer cancelled."
        return "There's no active timer."

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_set_command(self, text: str) -> Optional[int]:
        for pattern in _SET_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                duration = _parse_duration(m.group("value"), m.group("unit"))
                if duration:
                    return duration
        return None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._end_time is not None and not self._fired and not self._stopped

    @property
    def remaining_seconds(self) -> Optional[int]:
        with self._lock:
            if self._end_time is None:
                return None
            return max(0, int(self._end_time - time.time()))
