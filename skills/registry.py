"""
Skill registry — routes a transcribed utterance to the best-matching skill.

Skills register themselves; the registry calls match() on each and
picks the one with the highest confidence score (ties broken by priority).
"""

import logging
from typing import Optional, Tuple

from .base import Skill
from .timer import TimerSkill

log = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self, robot, expressions, tts) -> None:
        self._robot = robot
        self._expressions = expressions
        self._tts = tts

        # Register all skills here
        self._skills: list[Skill] = [
            TimerSkill(),
        ]

        log.info(f"Skill registry loaded: {[s.__class__.__name__ for s in self._skills]}")

    def handle(
        self,
        text: str,
        active_skill: Optional[Skill] = None,
    ) -> Tuple[Optional[Skill], str]:
        """
        Match `text` to the best skill and execute it.

        If `active_skill` is provided, it gets a chance to handle the command
        first (e.g. "reset" while a timer is running).

        Returns (skill_instance, spoken_response) or (None, "").
        """
        if not text:
            return None, ""

        text = text.lower().strip()

        # Active skill gets priority — it may handle follow-up commands
        if active_skill is not None:
            score = active_skill.match(text)
            if score >= 0.5:
                log.debug(f"Active skill {active_skill.__class__.__name__} handling: '{text}' (score={score:.2f})")
                response = active_skill.execute(text)
                self._react(active_skill, text)
                return active_skill, response

        # Find best-matching skill across all registered skills
        best_skill: Optional[Skill] = None
        best_score = 0.0

        for skill in self._skills:
            score = skill.match(text)
            log.debug(f"{skill.__class__.__name__}.match('{text}') = {score:.2f}")
            if score > best_score or (
                score == best_score
                and best_skill is not None
                and skill.priority > best_skill.priority
            ):
                best_score = score
                best_skill = skill

        if best_skill is None or best_score < 0.4:
            log.info(f"No skill matched '{text}' (best score={best_score:.2f})")
            return None, ""

        log.info(f"Matched {best_skill.__class__.__name__} for '{text}' (score={best_score:.2f})")
        response = best_skill.execute(text)
        self._react(best_skill, text)
        return best_skill, response

    def _react(self, skill: Skill, text: str) -> None:
        """Trigger appropriate robot expression for the skill+command."""
        if isinstance(skill, TimerSkill):
            from .timer import _STOP_PATTERN, _RESET_PATTERN
            if _STOP_PATTERN.search(text):
                self._expressions.on_timer_stopped()
            elif _RESET_PATTERN.search(text):
                self._expressions.on_timer_reset()
            else:
                self._expressions.on_timer_set()
