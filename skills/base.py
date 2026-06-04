"""
Base class for all skills.

Each skill must implement:
  - match(text) -> float     confidence that this skill handles the text (0.0–1.0)
  - execute(text) -> str     run the skill, return spoken response
  - poll() -> str | None     called each loop tick; return 'alarm', 'done', or None
  - is_dismiss_command(text) check if text should stop an active alarm
  - stop()                   cancel/cleanup the skill
"""

from abc import ABC, abstractmethod
from typing import Optional


class Skill(ABC):
    """Abstract base for all voice skills."""

    # Skills with higher priority win ties in the registry
    priority: int = 0

    @abstractmethod
    def match(self, text: str) -> float:
        """
        Return confidence (0.0–1.0) that this skill should handle `text`.
        0.0 = definitely not this skill.
        1.0 = definitely this skill.
        """
        ...

    @abstractmethod
    def execute(self, text: str) -> str:
        """
        Execute the skill based on transcribed text.
        Returns the spoken response string.
        """
        ...

    def poll(self) -> Optional[str]:
        """
        Called every ~100ms while this skill is the active skill.
        Return values:
          None     — still running, nothing to report
          'alarm'  — timer/alarm has fired, main loop should enter ALARMING state
          'done'   — skill has completed, main loop should return to IDLE
        """
        return "done"

    def is_dismiss_command(self, text: str) -> bool:
        """Return True if `text` should dismiss an active alarm."""
        return False

    def stop(self) -> None:
        """Cancel the skill cleanly."""
        pass
