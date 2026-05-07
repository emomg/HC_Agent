"""Self-Reasoning Engine -- Lightweight LLM-driven reflection for the agent.

Unlike MetaReflection (deep, periodic), SelfReasoner runs frequently with
minimal token cost to:
  1. Assess current progress toward goals
  2. Detect stuck/stalled patterns
  3. Update working memory with insights
  4. Suggest next actions or strategy shifts
"""
from __future__ import annotations
import time, json
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_core import LLMCore
    from memory.persistence import WorkingMemory


REASONING_PROMPT = """You are a self-reasoning module for an AI agent. Analyze the current situation concisely.

## Current Task
{task}

## Recent Activity (last {n_turns} turns)
{recent_history}

## Working Memory
{working_memory}

## Agent State
- Total turns: {total_turns}
- Errors: {error_count}
- Tools used: {tools_summary}
- Time elapsed: {elapsed:.1f}s

Respond in JSON:
{{
  "progress": "brief assessment of progress toward the goal",
  "stuck": false,
  "stuck_reason": "if stuck, why",
  "insight": "one key insight from this session",
  "suggested_action": "what to try next",
  "confidence": 0.0-1.0,
  "update_memory": {{"key": "value", ...}}
}}

Be extremely concise. One sentence per field. No verbose analysis."""


@dataclass
class ReasoningResult:
    """Result of a self-reasoning step."""
    progress: str = ""
    stuck: bool = False
    stuck_reason: str = ""
    insight: str = ""
    suggested_action: str = ""
    confidence: float = 0.5
    update_memory: dict = field(default_factory=dict)
    raw: str = ""
    timestamp: float = field(default_factory=time.time)


class SelfReasoner:
    """Lightweight self-reasoning engine.

    Call self_reason() periodically (e.g., every 3-5 turns) to get
    progress assessment and update working memory.
    """
    def __init__(self, llm: "LLMCore", working_memory: "WorkingMemory",
                 interval_turns: int = 5, min_interval_sec: float = 30.0):
        self._llm = llm
        self._wm = working_memory
        self._interval = interval_turns
        self._min_interval = min_interval_sec
        self._last_turn = 0
        self._last_time = 0.0
        self._history: list[ReasoningResult] = []

    def should_run(self, current_turn: int) -> bool:
        """Check if reasoning should run this turn."""
        if current_turn - self._last_turn < self._interval:
            return False
        if time.time() - self._last_time < self._min_interval:
            return False
        return True

    def reason(self, task: str, recent_records: list, state_summary: dict) -> Optional[ReasoningResult]:
        """Run a self-reasoning step. Returns None if LLM fails."""
        self._last_turn = state_summary.get("total_turns", 0)
        self._last_time = time.time()

        # Format recent history (last 5 turns, very concise)
        history_lines = []
        for rec in recent_records[-5:]:
            tool_info = f" -> {rec.tool_name}({rec.tool_result[:60]})" if rec.tool_name else ""
            think = rec.think[:80] if rec.think else ""
            answer = rec.answer[:80] if rec.answer else ""
            history_lines.append(f"  Think: {think}{tool_info}\n  Answer: {answer}")
        recent_str = "\n".join(history_lines) or "(no history yet)"

        prompt = REASONING_PROMPT.format(
            task=task[:300],
            n_turns=min(5, len(recent_records)),
            recent_history=recent_str,
            working_memory=self._wm.to_context_string(max_items=10),
            total_turns=state_summary.get("total_turns", 0),
            error_count=state_summary.get("error_count", 0),
            tools_summary=str(state_summary.get("tools_used", {})),
            elapsed=state_summary.get("elapsed", 0),
        )

        try:
            from llm_core import LLMMessage
            messages = [LLMMessage(role="system", content="You are a concise self-reasoning analyzer. Respond ONLY with valid JSON."),
                        LLMMessage(role="user", content=prompt)]
            resp = self._llm.ask(prompt, temperature=0.3, max_tokens=500)
            result = self._parse_response(resp.content if hasattr(resp, 'content') else str(resp))

            # Update working memory with any new insights
            if result.update_memory:
                for k, v in result.update_memory.items():
                    self._wm.set(k, str(v), category="insight", importance=result.confidence)

            if result.insight:
                self._wm.set(f"insight_t{self._last_turn}", result.insight,
                             category="insight", importance=result.confidence,
                             ttl=3600)  # expire in 1 hour

            self._history.append(result)
            return result

        except Exception:
            return None

    def _parse_response(self, text: str) -> ReasoningResult:
        """Parse LLM JSON response into ReasoningResult."""
        result = ReasoningResult(raw=text)
        # Extract JSON from response (handle markdown code blocks)
        text = text.strip()
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
        try:
            data = json.loads(text)
            result.progress = data.get("progress", "")
            result.stuck = data.get("stuck", False)
            result.stuck_reason = data.get("stuck_reason", "")
            result.insight = data.get("insight", "")
            result.suggested_action = data.get("suggested_action", "")
            result.confidence = float(data.get("confidence", 0.5))
            result.update_memory = data.get("update_memory", {})
        except (json.JSONDecodeError, ValueError):
            # Fallback: use raw text as insight
            result.insight = text[:200]
        return result

    def get_latest(self) -> Optional[ReasoningResult]:
        return self._history[-1] if self._history else None

    def get_suggestion(self) -> str:
        """Get latest suggested action for prompt injection."""
        r = self.get_latest()
        if r and r.suggested_action:
            return f"Suggested next: {r.suggested_action}"
        return ""
