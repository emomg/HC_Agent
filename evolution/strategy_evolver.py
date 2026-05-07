"""Strategy Evolver -- Dynamically evolves agent behavior based on experience.

Learns from reflection and failure data to:
  1. Generate context-specific prompt fragments
  2. Adjust reasoning strategy based on task type
  3. Build a library of effective strategies
  4. Inject learned lessons into system prompt dynamically

Instead of a static system prompt, the agent gets a "living" prompt
that adapts based on accumulated experience.
"""
from __future__ import annotations
import json, time, logging, os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from memory.store import MemoryStore

log = logging.getLogger("hc.evolution.strategy_evolver")

# Paths
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
BASE_PROMPT_PATH = os.path.join(ASSETS_DIR, "sys_prompt.txt")


@dataclass
class StrategyRule:
    """A learned strategy rule."""
    rule_id: str
    condition: str       # When to apply (task type, context keyword, etc.)
    instruction: str     # What to do differently
    source: str = ""     # Where this rule came from (reflection/failure/manual)
    effectiveness: float = 0.5  # 0.0-1.0, updated based on outcomes
    applications: int = 0
    successes: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = 0.0


@dataclass
class StrategyContext:
    """Context for strategy selection."""
    task_type: str = ""          # code/file/browser/data/system/general
    recent_failures: int = 0
    current_tools: list[str] = field(default_factory=list)
    session_length: int = 0
    domain: str = ""


class StrategyEvolver:
    """Evolves agent strategy based on accumulated experience.
    
    Usage:
        evolver = StrategyEvolver(store)
        prompt = evolver.build_adaptive_prompt(base_prompt, context)
        evolver.learn_from_outcome(rule_id, success=True)
    """
    
    def __init__(self, store: "MemoryStore"):
        self.store = store
        self.rules: dict[str, StrategyRule] = {}
        self._load_builtin_rules()
    
    def _load_builtin_rules(self):
        """Load built-in strategy rules from agent's own analysis."""
        builtins = [
            StrategyRule(
                rule_id="exploration_first",
                condition="task_type=any AND first_action",
                instruction="Before acting, probe the environment: read relevant files, check state, gather context. Never assume.",
                source="builtin:agent_self_analysis",
                effectiveness=0.9,
            ),
            StrategyRule(
                rule_id="failure_escalation",
                condition="recent_failures>=2",
                instruction="After 2 failures, switch strategy completely. Do NOT retry the same approach. Read SOP, check memory, or ask user.",
                source="builtin:agent_self_analysis",
                effectiveness=0.85,
            ),
            StrategyRule(
                rule_id="cross_validation",
                condition="task_type=data OR task_type=research",
                instruction="Never trust summaries or metadata. Always verify claims by reading the original source. Cross-check numbers.",
                source="builtin:agent_self_analysis",
                effectiveness=0.9,
            ),
            StrategyRule(
                rule_id="sop_first",
                condition="complexity=high",
                instruction="Before executing complex tasks, search for relevant SOPs. SOPs contain battle-tested procedures. Don't reinvent.",
                source="builtin:agent_self_analysis",
                effectiveness=0.8,
            ),
            StrategyRule(
                rule_id="incremental_execution",
                condition="task_type=code OR task_type=file",
                instruction="Execute step by step. After each step, verify the result before proceeding. Control failure radius.",
                source="builtin:agent_self_analysis",
                effectiveness=0.85,
            ),
            StrategyRule(
                rule_id="memory_checkpoint",
                condition="session_length>10",
                instruction="Long session detected. Update working checkpoint with current progress to prevent context loss.",
                source="builtin:agent_self_analysis",
                effectiveness=0.75,
            ),
        ]
        for rule in builtins:
            self.rules[rule.rule_id] = rule
    
    def build_adaptive_prompt(self, base_prompt: str, context: StrategyContext) -> str:
        """Build an enhanced system prompt with strategy injections.
        
        Args:
            base_prompt: Original system prompt text
            context: Current strategy context
            
        Returns:
            Enhanced prompt with strategy fragments appended
        """
        applicable = self._select_applicable_rules(context)
        
        if not applicable:
            return base_prompt
        
        # Build strategy section
        strategy_lines = [
            "",
            "## Adaptive Strategies (learned from experience)",
        ]
        
        # Sort by effectiveness (best first)
        applicable.sort(key=lambda r: r.effectiveness, reverse=True)
        
        for rule in applicable[:5]:  # Top 5 most relevant
            strategy_lines.append(
                f"- **{rule.rule_id}** ({rule.source}): {rule.instruction}"
            )
        
        # Add failure prevention hints if applicable
        if context.recent_failures > 0:
            strategy_lines.append("")
            strategy_lines.append(
                f"## Failure Prevention ({context.recent_failures} recent failures)"
            )
            strategy_lines.append(
                "Review your approach carefully. Consider alternative strategies."
            )
        
        return base_prompt + "\n".join(strategy_lines)
    
    def get_reasoning_modifiers(self, context: StrategyContext) -> dict:
        """Get reasoning modifiers for the current context.
        
        Returns dict of modifiers that adjust agent behavior:
        - extra_thinking: require more thinking before acting
        - prefer_alternatives: consider multiple approaches
        - verify_before_act: verify assumptions before tool call
        - break_down: break complex tasks into smaller steps
        """
        modifiers = {
            "extra_thinking": False,
            "prefer_alternatives": False,
            "verify_before_act": False,
            "break_down": False,
            "max_retries": 3,
        }
        
        if context.recent_failures >= 2:
            modifiers["extra_thinking"] = True
            modifiers["prefer_alternatives"] = True
            modifiers["max_retries"] = 1  # Fail fast, switch strategy
        
        if context.session_length > 15:
            modifiers["verify_before_act"] = True
        
        if context.task_type in ("code", "data"):
            modifiers["break_down"] = True
        
        return modifiers
    
    def learn_from_outcome(self, rule_id: str, success: bool):
        """Update rule effectiveness based on outcome.
        
        Args:
            rule_id: ID of the rule that was applied
            success: Whether the outcome was successful
        """
        if rule_id not in self.rules:
            return
        
        rule = self.rules[rule_id]
        rule.applications += 1
        rule.last_used = time.time()
        
        if success:
            rule.successes += 1
            # Increase effectiveness slightly
            rule.effectiveness = min(0.95, rule.effectiveness + 0.05)
        else:
            # Decrease effectiveness
            rule.effectiveness = max(0.1, rule.effectiveness - 0.1)
        
        log.info(
            f"[StrategyEvolver] Updated {rule_id}: "
            f"effectiveness={rule.effectiveness:.2f} "
            f"success_rate={rule.successes}/{rule.applications}"
        )
    
    def add_rule(self, rule: StrategyRule):
        """Add a new strategy rule learned from reflection."""
        self.rules[rule.rule_id] = rule
        self._store_rule(rule)
        log.info(f"[StrategyEvolver] Added new rule: {rule.rule_id}")
    
    def generate_rule_from_reflection(self, reflection: dict) -> Optional[StrategyRule]:
        """Generate a new strategy rule from a reflection report.
        
        Args:
            reflection: Structured reflection data from MetaReflection
            
        Returns:
            New StrategyRule if actionable lesson found, None otherwise
        """
        lessons = reflection.get("lessons", [])
        if not lessons:
            return None
        
        # Take the most impactful lesson
        lesson = lessons[0]
        rule_id = f"reflection_{int(time.time())}"
        
        rule = StrategyRule(
            rule_id=rule_id,
            condition=lesson.get("condition", "general"),
            instruction=lesson.get("action", "Apply learned lesson"),
            source="reflection",
            effectiveness=0.6,  # Start moderate, will be adjusted
        )
        
        self.add_rule(rule)
        return rule
    
    def get_strategy_report(self) -> dict:
        """Generate a report of all strategies and their effectiveness."""
        rules_list = sorted(
            self.rules.values(), key=lambda r: r.effectiveness, reverse=True
        )
        
        return {
            "total_rules": len(self.rules),
            "rules": [
                {
                    "id": r.rule_id,
                    "condition": r.condition,
                    "instruction": r.instruction[:100],
                    "effectiveness": r.effectiveness,
                    "applications": r.applications,
                    "source": r.source,
                }
                for r in rules_list
            ],
            "avg_effectiveness": (
                sum(r.effectiveness for r in self.rules.values()) / max(len(self.rules), 1)
            ),
        }
    
    def _select_applicable_rules(self, context: StrategyContext) -> list[StrategyRule]:
        """Select rules applicable to the current context."""
        applicable = []
        
        for rule in self.rules.values():
            if self._matches_context(rule, context):
                applicable.append(rule)
        
        return applicable
    
    def _matches_context(self, rule: StrategyRule, context: StrategyContext) -> bool:
        """Check if a rule matches the current context."""
        condition = rule.condition.lower()
        
        # Simple condition matching
        if "task_type=any" in condition:
            return True
        if f"task_type={context.task_type}" in condition:
            return True
        if "recent_failures>=" in condition:
            threshold = int(condition.split("recent_failures>=")[1].split()[0])
            if context.recent_failures >= threshold:
                return True
        if "session_length>" in condition:
            threshold = int(condition.split("session_length>")[1].split()[0])
            if context.session_length >= threshold:
                return True
        if "complexity=high" in condition:
            return context.session_length > 5
        if "first_action" in condition:
            return context.session_length <= 1
        
        return False
    
    def _store_rule(self, rule: StrategyRule):
        """Store rule in memory."""
        self.store.add(
            f"[STRATEGY] {rule.rule_id}: {rule.instruction}",
            layer=3, domain="strategy",
            source=rule.source,
            importance=rule.effectiveness * 0.8,
            tags=["strategy", "evolution"],
        )
