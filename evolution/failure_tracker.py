"""Failure Tracker -- Root cause analysis and anti-pattern library.

Goes beyond simple error counting to:
  1. Classify failures by root cause (not just count them)
  2. Extract anti-patterns to prevent repeating mistakes
  3. Track failure chains (cascade failures)
  4. Suggest recovery strategies based on past experience
  5. Build a growing library of "what not to do"

Philosophy: A failure is only wasted if you don't learn from it.
"""
from __future__ import annotations
import json, time, re, logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from memory.store import MemoryStore

log = logging.getLogger("hc.evolution.failure_tracker")


class FailureCategory(Enum):
    """Root cause categories for failure classification."""
    TOOL_ERROR = "tool_error"          # Tool call failed
    LOGIC_ERROR = "logic_error"        # Wrong reasoning/approach
    RESOURCE_ERROR = "resource_error"  # Missing file, permission, etc.
    TIMEOUT = "timeout"                # Operation timed out
    LOOP = "loop"                      # Agent got stuck repeating
    ESCALATION = "escalation"          # 3 failures, had to give up
    PARSING = "parsing"                # Failed to parse response
    UNKNOWN = "unknown"


@dataclass
class FailureRecord:
    """A single failure event with analysis."""
    failure_id: int
    turn: int
    timestamp: float
    category: FailureCategory
    tool_name: str = ""
    error_message: str = ""
    root_cause: str = ""
    context: str = ""          # What was the agent trying to do?
    recovery_action: str = ""  # What was done to recover?
    severity: float = 0.5      # 0.0 (minor) to 1.0 (critical)
    tags: list[str] = field(default_factory=list)


@dataclass
class AntiPattern:
    """A learned pattern of what NOT to do."""
    pattern_id: str
    description: str
    category: FailureCategory
    occurrences: int = 1
    last_seen: float = 0.0
    prevention_hint: str = ""  # How to avoid this pattern
    confidence: float = 0.5


# Error classification patterns
ERROR_PATTERNS = [
    (r"FileNotFoundError|No such file", FailureCategory.RESOURCE_ERROR, "missing_file"),
    (r"PermissionError|Access denied", FailureCategory.RESOURCE_ERROR, "permission"),
    (r"TimeoutError|timed?\s*out", FailureCategory.TIMEOUT, "timeout"),
    (r"SyntaxError|JSONDecodeError|parse", FailureCategory.PARSING, "parse_fail"),
    (r"ConnectionError|NetworkError|ECONNREFUSED", FailureCategory.TOOL_ERROR, "network"),
    (r"ModuleNotFoundError|ImportError", FailureCategory.RESOURCE_ERROR, "missing_module"),
    (r"KeyError|AttributeError|TypeError|ValueError", FailureCategory.LOGIC_ERROR, "type_mismatch"),
    (r"MemoryError|RecursionError", FailureCategory.RESOURCE_ERROR, "resource_exhaustion"),
    (r"loop|stuck|repeating|same error", FailureCategory.LOOP, "loop_detected"),
]


class FailureTracker:
    """Tracks, classifies, and learns from failures.
    
    Usage:
        tracker = FailureTracker(store)
        record = tracker.record_failure(turn=5, error="FileNotFoundError: ...", tool="file_read")
        hints = tracker.get_prevention_hints("file_read")
    """
    
    def __init__(self, store: "MemoryStore"):
        self.store = store
        self.failures: list[FailureRecord] = []
        self.anti_patterns: dict[str, AntiPattern] = {}
        self._failure_count = 0
        self._consecutive_failures = 0
    
    def record_failure(self, turn: int, error: str, tool: str = "",
                       context: str = "", severity: float = 0.5) -> FailureRecord:
        """Record and classify a failure.
        
        Args:
            turn: Turn number when failure occurred
            error: Error message/string
            tool: Tool that was being used
            context: What was the agent trying to do?
            severity: 0.0-1.0 how bad is this failure
            
        Returns:
            FailureRecord with classification
        """
        self._failure_count += 1
        self._consecutive_failures += 1
        
        category, tag = self._classify_error(error)
        root_cause = self._extract_root_cause(error, category)
        
        record = FailureRecord(
            failure_id=self._failure_count,
            turn=turn,
            timestamp=time.time(),
            category=category,
            tool_name=tool,
            error_message=error[:500],
            root_cause=root_cause,
            context=context,
            severity=severity,
            tags=[tag, tool] if tool else [tag],
        )
        
        self.failures.append(record)
        
        # Check for anti-pattern
        self._update_anti_patterns(record)
        
        # Store in memory
        self._store_failure(record)
        
        # Check for cascade/loop
        if self._consecutive_failures >= 3:
            self._record_escalation(turn)
        
        log.info(
            f"[FailureTracker] Recorded #{record.failure_id}: "
            f"{category.value} ({tag}) turn={turn} tool={tool} "
            f"consecutive={self._consecutive_failures}"
        )
        return record
    
    def record_success(self):
        """Record a successful action -- resets consecutive failure counter."""
        self._consecutive_failures = 0
    
    def get_prevention_hints(self, tool: str = None) -> list[str]:
        """Get hints to prevent known failure patterns.
        
        Args:
            tool: Optional tool name to filter hints for
            
        Returns:
            List of prevention hints
        """
        hints = []
        for pattern in self.anti_patterns.values():
            if tool and tool not in str(pattern.occurrences):
                continue
            if pattern.confidence >= 0.5:
                hints.append(
                    f"[AntiPattern] {pattern.description} -> {pattern.prevention_hint}"
                )
        return hints[:5]
    
    def get_failure_summary(self, last_n: int = 20) -> dict:
        """Get summary of recent failures for reflection prompts."""
        recent = self.failures[-last_n:]
        if not recent:
            return {"total": 0, "by_category": {}, "top_tools": []}
        
        by_cat = {}
        by_tool = {}
        for f in recent:
            cat = f.category.value
            by_cat[cat] = by_cat.get(cat, 0) + 1
            if f.tool_name:
                by_tool[f.tool_name] = by_tool.get(f.tool_name, 0) + 1
        
        top_tools = sorted(by_tool.items(), key=lambda x: -x[1])[:5]
        
        return {
            "total": len(recent),
            "by_category": by_cat,
            "top_tools": top_tools,
            "consecutive_failures": self._consecutive_failures,
            "anti_pattern_count": len(self.anti_patterns),
            "escalation_rate": sum(
                1 for f in recent if f.category == FailureCategory.ESCALATION
            ) / max(len(recent), 1),
        }
    
    def should_escalate(self, threshold: int = 3) -> bool:
        """Check if agent should escalate (give up current approach)."""
        return self._consecutive_failures >= threshold
    
    def get_recovery_suggestion(self, error: str, tool: str = "") -> str:
        """Suggest a recovery action based on past experience."""
        category, _ = self._classify_error(error)
        
        # Look for similar past failures and their recoveries
        similar = [
            f for f in self.failures[-50:]
            if f.category == category and f.recovery_action
        ]
        
        if similar:
            last_recovery = similar[-1].recovery_action
            return f"Past recovery: {last_recovery}"
        
        # Default suggestions by category
        suggestions = {
            FailureCategory.RESOURCE_ERROR: "Check file path exists, verify permissions",
            FailureCategory.TOOL_ERROR: "Try alternative tool or retry with different args",
            FailureCategory.LOGIC_ERROR: "Re-read the SOP, reconsider approach",
            FailureCategory.TIMEOUT: "Increase timeout or break into smaller operations",
            FailureCategory.LOOP: "Switch strategy completely, try different approach",
            FailureCategory.PARSING: "Simplify response format, add retry with stricter parsing",
            FailureCategory.ESCALATION: "Ask user for help -- agent cannot solve alone",
            FailureCategory.UNKNOWN: "Gather more info before retrying",
        }
        return suggestions.get(category, "Gather more info and retry")
    
    def _classify_error(self, error: str) -> tuple[FailureCategory, str]:
        """Classify an error string into a category."""
        error_lower = error.lower()
        for pattern, category, tag in ERROR_PATTERNS:
            if re.search(pattern, error_lower):
                return category, tag
        return FailureCategory.UNKNOWN, "unclassified"
    
    def _extract_root_cause(self, error: str, category: FailureCategory) -> str:
        """Extract root cause summary from error."""
        if category == FailureCategory.RESOURCE_ERROR:
            # Try to extract path
            path_match = re.search(r"['\"]([^'\"]+)['\"]", error)
            if path_match:
                return f"Missing resource: {path_match.group(1)}"
            return "Resource not available"
        elif category == FailureCategory.TOOL_ERROR:
            return f"Tool execution failed: {error[:100]}"
        elif category == FailureCategory.LOGIC_ERROR:
            return f"Logic/assumption error: {error[:100]}"
        elif category == FailureCategory.LOOP:
            return "Agent entered repetitive failure loop"
        return f"Error: {error[:150]}"
    
    def _update_anti_patterns(self, record: FailureRecord):
        """Update anti-pattern library from failure."""
        key = f"{record.category.value}:{record.tool_name}:{record.tags[0] if record.tags else 'unknown'}"
        
        if key in self.anti_patterns:
            pattern = self.anti_patterns[key]
            pattern.occurrences += 1
            pattern.last_seen = record.timestamp
            # Confidence increases with more occurrences
            pattern.confidence = min(0.95, pattern.confidence + 0.1)
        else:
            self.anti_patterns[key] = AntiPattern(
                pattern_id=key,
                description=f"{record.category.value} in {record.tool_name or 'general'}: {record.root_cause[:100]}",
                category=record.category,
                occurrences=1,
                last_seen=record.timestamp,
                prevention_hint=self.get_recovery_suggestion(
                    record.error_message, record.tool_name
                ),
                confidence=0.5,
            )
    
    def _record_escalation(self, turn: int):
        """Record that agent hit 3 consecutive failures."""
        escalation = FailureRecord(
            failure_id=self._failure_count + 1000,
            turn=turn,
            timestamp=time.time(),
            category=FailureCategory.ESCALATION,
            root_cause=f"Escalation after {self._consecutive_failures} consecutive failures",
            severity=0.8,
            tags=["escalation", "strategy_switch"],
        )
        self.failures.append(escalation)
        self._store_failure(escalation)
        log.warning(
            f"[FailureTracker] ESCALATION at turn {turn} "
            f"after {self._consecutive_failures} failures"
        )
    
    def _store_failure(self, record: FailureRecord):
        """Store failure in memory for future reference."""
        content = (
            f"[FAILURE-{record.category.value}] "
            f"Turn {record.turn}: {record.root_cause}"
        )
        if record.recovery_action:
            content += f" | Recovery: {record.recovery_action}"
        
        self.store.add(
            content,
            layer=2, domain="failure_tracker",
            source=f"failure_{record.failure_id}",
            importance=0.3 + record.severity * 0.5,
            tags=record.tags + ["failure"],
        )
