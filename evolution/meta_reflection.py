"""Meta-Reflection Engine -- LLM-driven deep reflection for self-evolution.

Unlike the mechanical ReflectionEngine that counts and thresholds,
MetaReflection uses the LLM to:
  1. Analyze recent interactions for strategic patterns
  2. Extract success strategies and failure root causes
  3. Generate actionable lessons stored as structured memory
  4. Track reflection quality over time

Designed as an enhancement layer on top of ReflectionEngine,
not a replacement -- both can coexist.

Architecture:
  MetaReflection.analyze(turns) 
    -> LLM prompt with interaction history
    -> Structured JSON response with lessons, strategies, warnings
    -> Stored in MemoryStore as L2 items with meta_reflection domain
    -> Can be retrieved by CDH budget allocator for future context
"""
from __future__ import annotations
import json, time, logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from llm_core import LLMCore, LLMMessage
    from memory.store import MemoryStore
    from agent_loop import TurnRecord

log = logging.getLogger("hc.evolution.meta_reflection")


@dataclass
class ReflectionReport:
    """Structured output from a meta-reflection cycle."""
    cycle: int
    timestamp: float
    success_patterns: list[str] = field(default_factory=list)
    failure_patterns: list[str] = field(default_factory=list)
    strategic_lessons: list[str] = field(default_factory=list)
    tool_effectiveness: dict[str, float] = field(default_factory=dict)
    suggested_improvements: list[str] = field(default_factory=list)
    confidence: float = 0.5
    raw_response: str = ""


@dataclass
class ReflectionTrend:
    """Tracks reflection quality and agent improvement over time."""
    total_cycles: int = 0
    lessons_learned: int = 0
    lessons_applied: int = 0
    failure_recurrence_rate: float = 0.0
    avg_confidence: float = 0.0


REFLECTION_PROMPT = """You are a meta-cognitive analyst reviewing an AI agent's recent interactions.

## Recent Interactions (last {n_turns} turns)
{interaction_history}

## Current Tool Proficiency
{tool_stats}

## Previously Learned Lessons
{known_lessons}

## Task
Analyze the interactions above and provide a structured reflection in JSON format:

{{
  "success_patterns": ["pattern1 describing what worked well and why"],
  "failure_patterns": ["pattern1 describing what failed and root cause analysis"],
  "strategic_lessons": ["actionable lesson the agent should internalize"],
  "tool_effectiveness": {{"tool_name": 0.0-1.0 rating}},
  "suggested_improvements": ["specific improvement suggestion"],
  "confidence": 0.0-1.0
}}

Focus on:
1. WHY certain approaches succeeded or failed (causal reasoning)
2. Patterns that repeat across multiple turns (meta-patterns)
3. Actionable advice, not vague observations
4. Tool selection appropriateness (was a better tool available?)
5. Compare with previously known lessons -- only add genuinely NEW insights

Be specific and evidence-based. Cite turn numbers when possible."""


class MetaReflectionEngine:
    """LLM-driven deep reflection that thinks about thinking.
    
    This is the "inner monologue" capability missing from the
    mechanical ReflectionEngine. It uses the LLM to perform
    causal analysis, pattern recognition, and strategic planning.
    
    Usage:
        meta = MetaReflectionEngine(llm, store)
        report = meta.analyze(recent_turns)
        # report contains structured lessons stored in memory
    """
    
    def __init__(self, llm: "LLMCore", store: "MemoryStore", 
                 max_turns_in_prompt: int = 20):
        self.llm = llm
        self.store = store
        self.max_turns = max_turns_in_prompt
        self.cycle_count = 0
        self.trend = ReflectionTrend()
        self._reports: list[ReflectionReport] = []
    
    def analyze(self, turns: list["TurnRecord"], 
                tool_stats: dict[str, float] = None) -> ReflectionReport:
        """Run a full meta-reflection cycle using LLM.
        
        Args:
            turns: Recent TurnRecords to analyze
            tool_stats: Optional tool_name -> effectiveness mapping
            
        Returns:
            ReflectionReport with structured findings
        """
        self.cycle_count += 1
        log.info(f"[MetaReflection] Starting cycle #{self.cycle_count}")
        
        # Prepare interaction history for the prompt
        history_text = self._format_turns(turns[-self.max_turns:])
        stats_text = self._format_tool_stats(tool_stats or {})
        lessons_text = self._format_known_lessons()
        
        prompt = REFLECTION_PROMPT.format(
            n_turns=min(len(turns), self.max_turns),
            interaction_history=history_text,
            tool_stats=stats_text,
            known_lessons=lessons_text,
        )
        
        # Call LLM for deep analysis
        try:
            response = self._call_llm(prompt)
            report = self._parse_response(response)
            report.cycle = self.cycle_count
            report.timestamp = time.time()
            report.raw_response = response
        except Exception as e:
            log.error(f"[MetaReflection] LLM call failed: {e}")
            report = ReflectionReport(
                cycle=self.cycle_count,
                timestamp=time.time(),
                confidence=0.0,
                raw_response=f"ERROR: {e}",
            )
        
        # Store findings in memory
        self._store_report(report)
        
        # Update trends
        self._update_trend(report)
        self._reports.append(report)
        
        log.info(
            f"[MetaReflection] Cycle #{self.cycle_count} done: "
            f"success={len(report.success_patterns)}, "
            f"failures={len(report.failure_patterns)}, "
            f"lessons={len(report.strategic_lessons)}, "
            f"confidence={report.confidence:.2f}"
        )
        return report
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM with the reflection prompt."""
        messages = [
            LLMMessage(role="system", content=(
                "You are an expert meta-cognitive analyst. "
                "Analyze the agent's interactions and respond ONLY with valid JSON."
            )),
            LLMMessage(role="user", content=prompt),
        ]
        resp = self.llm.chat(messages, temperature=0.3)
        return resp.content
    
    def _parse_response(self, raw: str) -> ReflectionReport:
        """Parse LLM JSON response into ReflectionReport."""
        # Try to extract JSON from response
        raw = raw.strip()
        if raw.startswith("```"):
            # Strip markdown code fences
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    return ReflectionReport(
                        cycle=self.cycle_count,
                        timestamp=time.time(),
                        raw_response=raw,
                        confidence=0.0,
                    )
            else:
                return ReflectionReport(
                    cycle=self.cycle_count,
                    timestamp=time.time(),
                    raw_response=raw,
                    confidence=0.0,
                )
        
        return ReflectionReport(
            cycle=self.cycle_count,
            timestamp=time.time(),
            success_patterns=data.get("success_patterns", []),
            failure_patterns=data.get("failure_patterns", []),
            strategic_lessons=data.get("strategic_lessons", []),
            tool_effectiveness=data.get("tool_effectiveness", {}),
            suggested_improvements=data.get("suggested_improvements", []),
            confidence=float(data.get("confidence", 0.5)),
            raw_response=raw,
        )
    
    def _store_report(self, report: ReflectionReport):
        """Store reflection findings as memory items."""
        # Store success patterns
        for pattern in report.success_patterns:
            self.store.add(
                f"[SUCCESS] {pattern}",
                layer=2, domain="meta_reflection",
                source=f"meta_reflect_cycle_{report.cycle}",
                importance=0.6 + report.confidence * 0.2,
                tags=["success_pattern", "meta_reflection"],
            )
        
        # Store failure patterns (higher importance to avoid repeating)
        for pattern in report.failure_patterns:
            self.store.add(
                f"[FAILURE] {pattern}",
                layer=2, domain="meta_reflection",
                source=f"meta_reflect_cycle_{report.cycle}",
                importance=0.7 + report.confidence * 0.2,
                tags=["failure_pattern", "meta_reflection", "avoid"],
            )
        
        # Store strategic lessons
        for lesson in report.strategic_lessons:
            self.store.add(
                f"[LESSON] {lesson}",
                layer=1, domain="meta_reflection",
                source=f"meta_reflect_cycle_{report.cycle}",
                importance=0.7 + report.confidence * 0.15,
                tags=["strategic_lesson", "meta_reflection"],
            )
            self.trend.lessons_learned += 1
        
        # Store improvement suggestions
        for imp in report.suggested_improvements:
            self.store.add(
                f"[IMPROVE] {imp}",
                layer=2, domain="meta_reflection",
                source=f"meta_reflect_cycle_{report.cycle}",
                importance=0.5 + report.confidence * 0.2,
                tags=["improvement", "meta_reflection"],
            )
    
    def _format_turns(self, turns: list["TurnRecord"]) -> str:
        """Format turns into a readable history for the LLM."""
        lines = []
        for t in turns:
            entry = f"Turn {t.turn}:"
            if t.think:
                entry += f"\n  Think: {t.think[:300]}"
            if t.tool_name:
                entry += f"\n  Tool: {t.tool_name}"
            if t.tool_args:
                args_str = json.dumps(t.tool_args, ensure_ascii=False)
                entry += f"\n  Args: {args_str[:200]}"
            if t.tool_result:
                entry += f"\n  Result: {t.tool_result[:300]}"
            if t.error:
                entry += f"\n  ERROR: {t.error[:200]}"
            lines.append(entry)
        return "\n".join(lines)
    
    def _format_tool_stats(self, stats: dict[str, float]) -> str:
        """Format tool effectiveness stats."""
        if not stats:
            return "No tool statistics available yet."
        lines = [f"  {name}: {score:.2f}" for name, score in stats.items()]
        return "\n".join(lines)
    
    def _format_known_lessons(self) -> str:
        """Retrieve and format previously learned lessons."""
        items = self.store.search("meta_reflection", domain="meta_reflection", top_k=10)
        if not items:
            return "No previously learned lessons."
        lessons = []
        for item in items:
            lessons.append(f"  [{item.tags[0] if item.tags else '?'}] {item.content[:150]}")
        return "\n".join(lessons[:10])
    
    def _update_trend(self, report: ReflectionReport):
        """Update reflection trend metrics."""
        self.trend.total_cycles += 1
        n = self.trend.total_cycles
        # Running average of confidence
        self.trend.avg_confidence = (
            (self.trend.avg_confidence * (n - 1) + report.confidence) / n
        )
    
    def get_trend(self) -> ReflectionTrend:
        """Get current reflection trend metrics."""
        return self.trend
    
    def get_recent_reports(self, n: int = 5) -> list[ReflectionReport]:
        """Get the most recent reflection reports."""
        return self._reports[-n:]
    
    def should_reflect(self, turns_since_last: int, 
                       frequency: int = 10) -> bool:
        """Determine if a reflection should be triggered.
        
        Uses adaptive frequency: reflect more often after failures,
        less often during smooth operation.
        """
        if turns_since_last < frequency:
            return False
        
        # Check recent failure rate
        recent_failures = sum(
            1 for r in self._reports[-3:]
            for _ in r.failure_patterns
        )
        if recent_failures > 3:
            # More failures -> reflect sooner
            return turns_since_last >= max(frequency // 2, 3)
        
        return True


# Alias for import compatibility (hc_agent.py and __init__.py import MetaReflection)
MetaReflection = MetaReflectionEngine
