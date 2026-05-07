"""Deep Thinker -- Multi-step reasoning before task execution.

Implements a structured deep-thinking phase that:
  1. Analyzes the task and decomposes into sub-problems
  2. Reasons through each sub-problem step by step
  3. Builds a comprehensive plan
  4. Stores the plan in working memory for the agent loop

Usage:
    from deep_thinker import DeepThinker, DeepThinkConfig
    thinker = DeepThinker(llm, config)
    result = thinker.think("Analyze this codebase")
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, List

log = logging.getLogger(__name__)


@dataclass
class DeepThinkConfig:
    """Configuration for deep thinking."""
    enabled: bool = False          # Enable deep thinking mode
    max_steps: int = 3             # Number of thinking steps (1-5)
    temperature: float = 0.3       # Lower temp for focused reasoning
    include_plan: bool = True      # Generate execution plan
    include_risks: bool = True     # Analyze potential risks
    timeout: float = 120.0         # Max thinking time in seconds


@dataclass
class ThinkStep:
    """A single thinking step."""
    step_num: int
    question: str
    reasoning: str
    conclusion: str


@dataclass
class ThinkResult:
    """Result of the deep thinking phase."""
    analysis: str                  # High-level task analysis
    steps: List[ThinkStep] = field(default_factory=list)
    plan: str = ""                 # Execution plan
    risks: str = ""                # Risk analysis
    key_insights: List[str] = field(default_factory=list)
    total_tokens: int = 0
    elapsed: float = 0.0


# -- Thinking prompt templates --

ANALYSIS_PROMPT = """You are a deep reasoning engine. Analyze the following task carefully.

Task: {task}

Context: {context}

Think step by step:
1. What is the core objective?
2. What are the key sub-problems?
3. What approach would be most effective?

Respond in JSON:
{{
  "analysis": "high-level analysis of the task",
  "sub_problems": ["sub-problem 1", "sub-problem 2"],
  "approach": "recommended approach"
}}"""

STEP_PROMPT = """Continue deep reasoning. Previous analysis:
{previous_analysis}

Sub-problem to solve: {sub_problem}

Think deeply about this. What is the best solution? What are the tradeoffs?

Respond in JSON:
{{
  "reasoning": "detailed reasoning chain",
  "conclusion": "conclusion for this sub-problem",
  "insight": "key insight gained"
}}"""

PLAN_PROMPT = """Based on the deep thinking analysis below, create a concrete execution plan.

Analysis: {analysis}
Key insights: {insights}

Create a step-by-step execution plan. Be specific about what actions to take and in what order.

Respond in JSON:
{{
  "plan": "detailed step-by-step execution plan",
  "risks": "potential risks and mitigations",
  "priority_order": ["step 1", "step 2"]
}}"""


class DeepThinker:
    """Multi-step deep reasoning engine."""

    def __init__(self, llm, config: DeepThinkConfig = None):
        """
        Args:
            llm: LLMCore instance (must have .chat() method)
            config: DeepThinkConfig instance
        """
        self.llm = llm
        self.config = config or DeepThinkConfig()
        self.enabled = self.config.enabled  # used by stapp.py toggle
        self._history: List[ThinkResult] = []

    def think(self, task: str, context: str = "") -> Optional[ThinkResult]:
        """Run deep thinking on a task.

        Args:
            task: The user's task description
            context: Additional context (e.g., memory summary)

        Returns:
            ThinkResult or None if disabled/failed
        """
        if not self.enabled:
            return None

        start = time.time()
        total_tokens = 0

        try:
            # Step 1: Analyze task
            log.info(f"[DeepThink] Starting analysis for: {task[:60]}...")
            analysis_resp = self.llm.chat(
                ANALYSIS_PROMPT.format(task=task, context=context),
                temperature=self.config.temperature,
            )
            total_tokens += getattr(analysis_resp, "usage", {}).get("total_tokens", 0)

            parsed = self._parse_json(analysis_resp.content)
            analysis = parsed.get("analysis", analysis_resp.content)
            sub_problems = parsed.get("sub_problems", [])
            approach = parsed.get("approach", "")

            # Step 2: Think through sub-problems
            steps = []
            previous_context = f"Analysis: {analysis}\nApproach: {approach}"

            for i, sp in enumerate(sub_problems[: self.config.max_steps]):
                log.info(f"[DeepThink] Step {i+1}: {sp[:60]}...")
                step_resp = self.llm.chat(
                    STEP_PROMPT.format(
                        previous_analysis=previous_context,
                        sub_problem=sp,
                    ),
                    temperature=self.config.temperature,
                )
                total_tokens += getattr(step_resp, "usage", {}).get("total_tokens", 0)

                step_parsed = self._parse_json(step_resp.content)
                step = ThinkStep(
                    step_num=i + 1,
                    question=sp,
                    reasoning=step_parsed.get("reasoning", step_resp.content),
                    conclusion=step_parsed.get("conclusion", ""),
                )
                steps.append(step)

                # Accumulate context for next step
                previous_context += f"\n\nStep {i+1} ({sp}): {step.conclusion}"

            # Step 3: Generate plan
            plan_text = ""
            risks_text = ""
            insights = [s.conclusion for s in steps if s.conclusion]

            if self.config.include_plan:
                log.info("[DeepThink] Generating execution plan...")
                insights_str = "\n".join(f"- {i}" for i in insights)
                plan_resp = self.llm.chat(
                    PLAN_PROMPT.format(
                        analysis=analysis,
                        insights=insights_str,
                    ),
                    temperature=self.config.temperature,
                )
                total_tokens += getattr(plan_resp, "usage", {}).get("total_tokens", 0)

                plan_parsed = self._parse_json(plan_resp.content)
                plan_text = plan_parsed.get("plan", plan_resp.content)
                risks_text = plan_parsed.get("risks", "")

            elapsed = time.time() - start

            result = ThinkResult(
                analysis=analysis,
                steps=steps,
                plan=plan_text,
                risks=risks_text,
                key_insights=insights,
                total_tokens=total_tokens,
                elapsed=elapsed,
            )

            self._history.append(result)
            log.info(f"[DeepThink] Complete: {len(steps)} steps, {total_tokens} tokens, {elapsed:.1f}s")

            return result

        except Exception as e:
            log.warning(f"[DeepThink] Failed: {e}")
            return None

    def format_for_prompt(self, result: ThinkResult) -> str:
        """Format thinking result for injection into agent prompt.

        Args:
            result: ThinkResult from think()

        Returns:
            Formatted string for prompt injection
        """
        if not result:
            return ""

        parts = ["[Deep Thinking Analysis]", ""]

        parts.append(f"Analysis: {result.analysis}")
        parts.append("")

        if result.steps:
            parts.append("Reasoning Steps:")
            for step in result.steps:
                parts.append(f"  {step.step_num}. {step.question}")
                parts.append(f"     -> {step.conclusion}")
            parts.append("")

        if result.plan:
            parts.append(f"Execution Plan:\n{result.plan}")
            parts.append("")

        if result.risks:
            parts.append(f"Risks: {result.risks}")

        return "\n".join(parts)

    def get_stats(self) -> dict:
        """Get thinking statistics."""
        if not self._history:
            return {"count": 0}
        latest = self._history[-1]
        return {
            "count": len(self._history),
            "last_steps": len(latest.steps),
            "last_tokens": latest.total_tokens,
            "last_elapsed": f"{latest.elapsed:.1f}s",
        }

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = text.strip()
        # Try to extract from code block
        if "```" in text:
            parts = text.split("```")
            for part in parts[1::2]:  # odd indices are inside blocks
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    continue
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
