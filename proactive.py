"""Proactive Manager -- Agent-initiated task triggers and autonomous invocation.

Provides:
  1. Trigger rules: condition-based task auto-generation
  2. Periodic checks: idle detection, goal monitoring, stuck detection
  3. Task queue: prioritized queue of self-initiated tasks
  4. Integration point: called from agent_loop._tick()
"""
from __future__ import annotations
import time, json, threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from memory.persistence import WorkingMemory


class TriggerType(Enum):
    IDLE = "idle"              # No user input for N seconds
    STUCK = "stuck"            # Agent stuck for N turns
    GOAL_DRIFT = "goal_drift"  # Deviating from stated goal
    ERROR_SPIKE = "error_spike"  # Too many errors in window
    INSIGHT = "insight"        # Self-reasoner found something noteworthy
    SCHEDULED = "scheduled"    # Time-based trigger
    CUSTOM = "custom"          # User-defined trigger


@dataclass
class ProactiveTask:
    """A self-initiated task."""
    id: str
    trigger: TriggerType
    description: str
    priority: float = 0.5       # [0,1], higher = more urgent
    created_at: float = field(default_factory=time.time)
    executed: bool = False
    result: str = ""


@dataclass
class TriggerRule:
    """A condition that generates proactive tasks."""
    name: str
    trigger_type: TriggerType
    condition: Callable[["ProactiveManager", dict], bool]
    task_template: str          # f-string style with {context}
    priority: float = 0.5
    cooldown_sec: float = 60.0
    last_fired: float = 0.0
    enabled: bool = True


class ProactiveManager:
    """Manages proactive triggers and self-initiated tasks.

    Call check(state) periodically from agent_loop to evaluate triggers
    and generate tasks. Call get_pending_tasks() to retrieve tasks.
    """
    def __init__(self, working_memory: "WorkingMemory" = None,
                 idle_threshold_sec: float = 120.0,
                 stuck_threshold_turns: int = 5,
                 error_spike_threshold: int = 5):
        self._wm = working_memory
        self._idle_threshold = idle_threshold_sec
        self._stuck_threshold = stuck_threshold_turns
        self._error_spike = error_spike_threshold
        self._tasks: list[ProactiveTask] = []
        self._rules: list[TriggerRule] = []
        self._task_counter = 0
        self._last_user_input = time.time()
        self._turns_since_progress = 0
        self._last_error_count = 0

        # Register default rules
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default trigger rules."""
        self._rules = [
            TriggerRule(
                name="idle_exploration",
                trigger_type=TriggerType.IDLE,
                condition=lambda mgr, s: (time.time() - mgr._last_user_input) > mgr._idle_threshold,
                task_template="Agent has been idle for {idle_sec:.0f}s. Consider: reviewing working memory, organizing notes, or exploring the codebase.",
                priority=0.3,
                cooldown_sec=300,
            ),
            TriggerRule(
                name="stuck_alert",
                trigger_type=TriggerType.STUCK,
                condition=lambda mgr, s: mgr._turns_since_progress >= mgr._stuck_threshold,
                task_template="Agent appears stuck after {stuck_turns} turns without progress. Suggest: try a different approach, break the problem down, or ask the user for clarification.",
                priority=0.8,
                cooldown_sec=120,
            ),
            TriggerRule(
                name="error_spike",
                trigger_type=TriggerType.ERROR_SPIKE,
                condition=lambda mgr, s: s.get("error_count", 0) - mgr._last_error_count >= mgr._error_spike,
                task_template="Error spike detected: {new_errors} new errors. Review error patterns and consider adjusting strategy.",
                priority=0.7,
                cooldown_sec=60,
            ),
            TriggerRule(
                name="goal_review",
                trigger_type=TriggerType.GOAL_DRIFT,
                condition=lambda mgr, s: (s.get("total_turns", 0) > 0 and
                                          s.get("total_turns", 0) % 15 == 0),
                task_template="Periodic goal review at turn {turn}. Check if current actions align with stated goal.",
                priority=0.4,
                cooldown_sec=300,
            ),
        ]

    def notify_user_input(self) -> None:
        """Call when user provides input. Resets idle timer and progress counter."""
        self._last_user_input = time.time()
        self._turns_since_progress = 0

    def notify_progress(self) -> None:
        """Call when agent makes meaningful progress (tool success, answer)."""
        self._turns_since_progress = 0

    def notify_turn(self) -> None:
        """Call at each turn to increment stuck counter."""
        self._turns_since_progress += 1

    def add_rule(self, rule: TriggerRule) -> None:
        """Add a custom trigger rule."""
        self._rules.append(rule)

    def check(self, state: dict) -> list[ProactiveTask]:
        """Evaluate all trigger rules against current state. Returns new tasks."""
        now = time.time()
        new_tasks = []
        context = {
            "idle_sec": now - self._last_user_input,
            "stuck_turns": self._turns_since_progress,
            "turn": state.get("total_turns", 0),
            "error_count": state.get("error_count", 0),
            "new_errors": state.get("error_count", 0) - self._last_error_count,
            "elapsed": state.get("elapsed", 0),
        }

        for rule in self._rules:
            if not rule.enabled:
                continue
            if now - rule.last_fired < rule.cooldown_sec:
                continue
            try:
                if rule.condition(self, state):
                    task = self._make_task(rule, context)
                    new_tasks.append(task)
                    rule.last_fired = now
            except Exception:
                continue

        self._last_error_count = state.get("error_count", 0)
        self._tasks.extend(new_tasks)
        return new_tasks

    def get_pending_tasks(self, max_tasks: int = 3) -> list[ProactiveTask]:
        """Get highest-priority unexecuted tasks."""
        pending = [t for t in self._tasks if not t.executed]
        pending.sort(key=lambda t: t.priority, reverse=True)
        return pending[:max_tasks]

    def get_suggestions(self, max_suggestions: int = 3) -> list[str]:
        """Get proactive suggestions as strings for prompt injection."""
        pending = self.get_pending_tasks(max_suggestions)
        return [t.description for t in pending]

    def mark_executed(self, task_id: str, result: str = "") -> None:
        """Mark a task as executed with result."""
        for t in self._tasks:
            if t.id == task_id:
                t.executed = True
                t.result = result
                break

    def prune(self, max_age_sec: float = 3600) -> int:
        """Remove old executed tasks."""
        now = time.time()
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks
                       if not t.executed or (now - t.created_at) < max_age_sec]
        return before - len(self._tasks)

    def _make_task(self, rule: TriggerRule, context: dict) -> ProactiveTask:
        self._task_counter += 1
        desc = rule.task_template.format(**context)
        return ProactiveTask(
            id=f"proactive_{self._task_counter}",
            trigger=rule.trigger_type,
            description=desc,
            priority=rule.priority,
        )


# Aliases
ProactiveTrigger = ProactiveManager
