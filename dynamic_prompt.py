"""Dynamic Prompt Builder -- Assembles system prompt from context.

Replaces the static sys_prompt.txt with a context-aware prompt that includes:
  1. Base template (from sys_prompt.txt)
  2. Working memory context
  3. Agent state (turns, errors, tools used)
  4. Self-reasoning insights
  5. Relevant memory items (CDH-selected)
"""
from __future__ import annotations
import os, time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.persistence import WorkingMemory
    from self_reasoner import SelfReasoner, ReasoningResult


BASE_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "assets", "sys_prompt.txt")

STATE_TEMPLATE = """
## Current Session State
- Turn: {turn}/{max_turns}
- Errors: {error_count}
- Tools used this session: {tools_summary}
- Elapsed: {elapsed:.0f}s
"""

PROACTIVE_TEMPLATE = """
## Proactive Suggestions
{suggestions}
"""


class DynamicPromptBuilder:
    """Builds a dynamic system prompt from base template + context layers.

    Usage:
        builder = DynamicPromptBuilder(base_prompt_path="assets/sys_prompt.txt")
        system_msg = builder.build(
            working_memory=wm,
            state=state_dict,
            reasoner=reasoner,
            memory_context="...",
        )
    """
    def __init__(self, base_prompt_path: str = None):
        self._base_path = base_prompt_path or BASE_PROMPT_PATH
        self._base_cache: str = None

    def _load_base(self) -> str:
        if self._base_cache is not None:
            return self._base_cache
        try:
            with open(self._base_path, "r", encoding="utf-8") as f:
                self._base_cache = f.read()
        except FileNotFoundError:
            self._base_cache = "You are HC Agent, a helpful AI assistant with tools."
        return self._base_cache

    def build(self,
              working_memory: "WorkingMemory" = None,
              state: dict = None,
              reasoner: "SelfReasoner" = None,
              memory_context: str = "",
              proactive_suggestions: list[str] = None,
              ) -> str:
        """Build the full dynamic system prompt."""
        parts = [self._load_base()]

        # Layer 1: Agent state
        if state:
            parts.append(STATE_TEMPLATE.format(
                turn=state.get("turn", 0),
                max_turns=state.get("max_turns", 50),
                error_count=state.get("error_count", 0),
                tools_summary=str(state.get("tools_used", {})),
                elapsed=state.get("elapsed", 0),
            ))

        # Layer 2: Working memory
        if working_memory:
            wm_str = working_memory.to_context_string(max_items=15)
            if wm_str:
                parts.append(wm_str)

        # Layer 3: Self-reasoning insights
        if reasoner:
            suggestion = reasoner.get_suggestion()
            if suggestion:
                parts.append(f"\n## Self-Reflection\n{suggestion}")
            latest = reasoner.get_latest()
            if latest and latest.stuck:
                parts.append(f"\n**WARNING**: Agent appears stuck. Reason: {latest.stuck_reason}")
                parts.append("Consider changing strategy, trying a different approach, or asking for help.")

        # Layer 4: Memory context (from CDH allocation)
        if memory_context:
            parts.append(f"\n## Relevant Memory\n{memory_context}")

        # Layer 5: Proactive suggestions
        if proactive_suggestions:
            sug_text = "\n".join(f"- {s}" for s in proactive_suggestions)
            parts.append(PROACTIVE_TEMPLATE.format(suggestions=sug_text))

        return "\n".join(parts)

    def invalidate_cache(self) -> None:
        """Force re-read of base prompt on next build."""
        self._base_cache = None


# Alias
PromptBuilder = DynamicPromptBuilder
