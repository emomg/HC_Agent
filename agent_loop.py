"""Agent Loop — ReAct reasoning with Inner Monologue.

The agent loop implements:
  1. Perceive  — build context via CDH budget allocation
  2. Think     — Inner Monologue reasoning step
  3. Act       — select and execute tool
  4. Observe   — process tool result
  5. Reflect   — every 10 turns, run reflection cycle

Inner Monologue format:
  <think>reasoning about what to do next</think>
  <tool>{"name": "...", "args": {...}}</tool>
  <answer>final answer when task complete</answer>
"""
from __future__ import annotations
import json, re, time, logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config import HCConfig
    from llm_core import LLMCore, LLMMessage
    from tools import ToolRegistry
    from memory.store import MemoryStore
    from memory.budget import CDHBudgetManager
    from memory.persistence import WorkingMemory, MemoryStorePersistence
    from evolution.reflection import ReflectionEngine
    from evolution.failure_tracker import FailureTracker
    from evolution.experience_replay import ExperienceReplay
    from self_reasoner import SelfReasoner
    from dynamic_prompt import DynamicPromptBuilder
    from proactive import ProactiveManager
    from deep_thinker import DeepThinker

log = logging.getLogger("hc_agent.loop")


@dataclass
class TurnRecord:
    """Record of one agent turn."""
    turn: int
    think: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    answer: str = ""
    timestamp: float = 0.0
    tokens_used: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class LoopState:
    """Persistent state of the agent loop."""
    task: str = ""
    turns: list[TurnRecord] = field(default_factory=list)
    done: bool = False
    final_answer: str = ""
    total_tokens: int = 0
    error_count: int = 0
    start_time: float = 0.0

    def __post_init__(self):
        if not self.start_time:
            self.start_time = time.time()


class AgentLoop:
    """ReAct agent loop with Inner Monologue."""
    
    def __init__(self, config: "HCConfig", llm: "LLMCore",
                 tools: "ToolRegistry", store: "MemoryStore",
                 budget_mgr: "CDHBudgetManager",
                 reflection_engine: "ReflectionEngine" = None,
                 failure_tracker: "FailureTracker" = None,
                 experience_replay: "ExperienceReplay" = None,
                 working_memory: "WorkingMemory" = None,
                 self_reasoner: "SelfReasoner" = None,
                 dynamic_prompt: "DynamicPromptBuilder" = None,
                 proactive: "ProactiveManager" = None,
                 persistence: "MemoryStorePersistence" = None,
                 deep_thinker: "DeepThinker" = None):
        self.config = config
        self.llm = llm
        self.tools = tools
        self.store = store
        self.budget_mgr = budget_mgr
        self.reflection = reflection_engine
        self.failure_tracker = failure_tracker
        self.experience_replay = experience_replay
        self.working_memory = working_memory
        self.self_reasoner = self_reasoner
        self.dynamic_prompt = dynamic_prompt
        self.proactive = proactive
        self.persistence = persistence
        self.deep_thinker = deep_thinker
        self.state = LoopState()
    
    def run(self, task: str, max_turns: int = None, on_token: callable = None) -> str:
        """Execute a task through the ReAct loop.
        
        Args:
            on_token: Optional callback for streaming LLM output (called with each text chunk).
        Returns the final answer string.
        """
        self._on_token = on_token
        max_turns = max_turns or self.config.agent.max_turns
        self.state = LoopState(task=task)
        
        # Store task as memory + working memory
        self.store.add(f"Task: {task}", layer=0, domain="task",
                       source="agent_loop", importance=0.9)
        if self.working_memory:
            self.working_memory.set("current_task", task, category="goal", importance=0.9)
        if self.proactive:
            self.proactive.notify_user_input()
        
        # Deep thinking phase: multi-step reasoning before execution
        if self.deep_thinker and self.deep_thinker.enabled:
            log.info("[Loop] Deep thinking phase started...")
            dt_result = self.deep_thinker.think(task)
            if dt_result:
                dt_raw = dt_result.plan if dt_result.plan else (dt_result.analysis or "")
                self.store.add(
                    f"Deep think for '{task[:50]}': {dt_raw[:500]}",
                    layer=1, domain="reasoning",
                    source="deep_thinker", importance=0.8,
                )
            log.info("[Loop] Deep thinking completed.")
        
        log.info(f"[Loop] Starting task: {task[:80]}...")
        
        while not self.state.done and len(self.state.turns) < max_turns:
            turn_num = len(self.state.turns) + 1
            
            try:
                record = self._execute_turn(turn_num)
                self.state.turns.append(record)
                
                # Check for final answer
                if record.answer:
                    self.state.done = True
                    self.state.final_answer = record.answer
                    break
                
                # Notify proactive of turn completion
                if self.proactive:
                    self.proactive.notify_turn()
                    if record.tool_result and "error" not in record.tool_result.lower():
                        self.proactive.notify_progress()
                
                # Periodic reflection (every N turns)
                if self.reflection and turn_num % 10 == 0:
                    self._run_reflection(turn_num)
                
                # Self-reasoning (lightweight, more frequent)
                if self.self_reasoner and self.self_reasoner.should_run(turn_num):
                    self._run_self_reasoning(turn_num)
                
                # Proactive task check (every 5 turns)
                if self.proactive and turn_num % 5 == 0:
                    self._check_proactive(turn_num)
                
            except Exception as e:
                log.error(f"[Loop] Turn {turn_num} error: {e}")
                self.state.error_count += 1
                if self.state.error_count >= 3:
                    self.state.done = True
                    self.state.final_answer = f"Task failed after {turn_num} turns: {e}"
                    break
        
        # Save state to working memory
        if self.working_memory:
            self.working_memory.set("last_task_result", self.state.final_answer[:500],
                                     category="state", importance=0.7)
            self.working_memory.set("last_task_turns", str(len(self.state.turns)),
                                     category="state", importance=0.5)
        
        # Persist memory store
        if self.persistence:
            self.persistence.save_now()
        
        # Final summary
        elapsed = time.time() - self.state.start_time
        summary = self._build_summary(elapsed)
        log.info(f"[Loop] Completed in {elapsed:.1f}s, {len(self.state.turns)} turns")
        
        return self.state.final_answer
    
    def _execute_turn(self, turn_num: int) -> TurnRecord:
        """Execute a single ReAct turn."""
        record = TurnRecord(turn=turn_num)
        
        # 1. Perceive — build context
        messages = self._build_messages(turn_num)
        
        # 2. Think — call LLM (stream tokens if callback provided)
        on_token = getattr(self, '_on_token', None)
        response = self.llm.chat(messages, tools=self.tools.get_schemas(), on_token=on_token)
        record.tokens_used = response.usage.get("total_tokens", 0)
        self.state.total_tokens += record.tokens_used
        
        # 3. Parse response
        if response.tool_calls:
            # Tool call mode
            tc = response.tool_calls[0]
            record.tool_name = tc["name"]
            try:
                record.tool_args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                record.tool_args = {"raw": tc["arguments"]}
            
            # Think content
            record.think = response.content or f"Calling tool: {tc['name']}"
            
            # 4. Act — execute tool
            context = {"memory_store": self.store}
            result = self.tools.execute(record.tool_name, record.tool_args, context)
            record.tool_result = result
            
            # Track failures for meta-reflection
            is_failure = "error" in result.lower() or "exception" in result.lower()
            if is_failure and self.failure_tracker:
                self.failure_tracker.track(
                    tool_name=record.tool_name,
                    error_msg=result[:500],
                    args=record.tool_args,
                    context={"turn": turn_num, "task": self.state.task[:200]},
                )
            
            # Record successful experiences for replay
            if not is_failure and self.experience_replay and record.think:
                try:
                    self.experience_replay.store_experience(
                        task_summary=self.state.task[:200],
                        strategy=record.think[:500],
                        tools=[record.tool_name] if record.tool_name else [],
                        outcome="success",
                        decisions=[],
                        lessons=[f"Tool {record.tool_name}: {str(record.tool_args)[:200]}"],
                    )
                except Exception as e:
                    log.debug(f"Experience record failed: {e}")
            
            # 5. Observe — store result in working memory
            self.store.add(
                f"[T{turn_num}] {record.tool_name}({json.dumps(record.tool_args, ensure_ascii=False)[:100]}) → {result[:200]}",
                layer=0, domain="execution", source="tool_result",
                importance=0.3,
            )
            
            # Add tool result to history for next turn
            self._append_tool_message(tc["id"], record.tool_name, result)
            
        else:
            # Text response — check for Inner Monologue format
            content = response.content
            record.think = self._extract_tag(content, "think")
            record.answer = self._extract_tag(content, "answer")
            
            if record.think and not record.answer:
                # Has think but no answer tag — extract text after think block
                import re
                stripped = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                if stripped:
                    record.answer = stripped
                else:
                    record.answer = record.think
            
            if not record.think and not record.answer:
                # Plain text — treat as final answer
                record.answer = content
        
        return record
    
    def _build_messages(self, turn_num: int) -> list[LLMMessage]:
        """Build message list with CDH budget-managed context."""
        from llm_core import LLMMessage
        
        messages = []
        
        # System prompt (dynamic if available, else static)
        if self.dynamic_prompt:
            elapsed = time.time() - self.state.start_time
            tools_used = {}
            for rec in self.state.turns:
                if rec.tool_name:
                    tools_used[rec.tool_name] = tools_used.get(rec.tool_name, 0) + 1
            state_dict = {
                "turn": turn_num,
                "max_turns": self.config.agent.max_turns,
                "error_count": self.state.error_count,
                "tools_used": tools_used,
                "elapsed": elapsed,
                "total_turns": turn_num,
            }
            # Get proactive suggestions
            pro_suggestions = self.proactive.get_suggestions(3) if self.proactive else None
            sys_prompt = self.dynamic_prompt.build(
                working_memory=self.working_memory,
                state=state_dict,
                reasoner=self.self_reasoner,
                proactive_suggestions=pro_suggestions,
            )
        else:
            sys_prompt = self._load_system_prompt()
        messages.append(LLMMessage(role="system", content=sys_prompt))
        
        # CDH-allocated context
        query = self.state.task
        if self.state.turns:
            # Use last turn's reasoning as context query
            last = self.state.turns[-1]
            query = last.think or last.tool_result or self.state.task
        
        alloc = self.budget_mgr.allocate(query, self.store)
        context_str = self.budget_mgr.format_context(alloc)
        
        if context_str:
            messages.append(LLMMessage(
                role="system",
                content=f"[Memory Context]\n{context_str}"
            ))
        
        # Inject similar experiences for strategy replay
        if self.experience_replay and turn_num > 1:
            try:
                similar = self.experience_replay.retrieve_for_failure(
                    failure_type="general", context=query
                )
            except Exception:
                similar = None
            if similar:
                exp_str = self.experience_replay.format_for_prompt(similar)
                messages.append(LLMMessage(
                    role="system",
                    content=f"[Similar Past Experiences]\n{exp_str}"
                ))
        
        # Conversation history (last N turns)
        for rec in self.state.turns[-self.config.agent.max_history_turns:]:
            if rec.think:
                think_block = f"<think>{rec.think}</think>"
                if rec.tool_name:
                    tool_block = f'<tool>{{"name": "{rec.tool_name}", "args": {json.dumps(rec.tool_args, ensure_ascii=False)}}}</tool>'
                    messages.append(LLMMessage(
                        role="assistant", content=think_block + "\n" + tool_block,
                        tool_calls=[{
                            "id": f"call_{rec.turn}",
                            "type": "function",
                            "function": {"name": rec.tool_name, "arguments": json.dumps(rec.tool_args, ensure_ascii=False)}
                        }]))
                else:
                    messages.append(LLMMessage(role="assistant", content=think_block))
            
            if rec.tool_result:
                messages.append(LLMMessage(role="tool", content=rec.tool_result,
                                           tool_call_id=f"call_{rec.turn}"))
            
            if rec.answer and not rec.tool_name:
                messages.append(LLMMessage(role="assistant", content=f"<answer>{rec.answer}</answer>"))
        
        # User task — MUST be included so LLM receives actual user input
        if not self.state.turns:
            # First turn: add the original task as user message
            messages.append(LLMMessage(role="user", content=self.state.task))
        else:
            # Subsequent turns: add a continuation prompt
            last = self.state.turns[-1]
            if last.tool_result:
                # Tool result already added above; add follow-up user instruction
                messages.append(LLMMessage(role="user", content="Continue based on the result above."))
        
        return messages
    
    def _append_tool_message(self, call_id: str, name: str, result: str):
        """Add tool call and result to message history for LLM context."""
        # This is handled in _build_messages via TurnRecord
        pass
    
    def _load_system_prompt(self) -> str:
        """Load system prompt from assets."""
        from pathlib import Path
        prompt_path = Path(__file__).parent / "assets" / "sys_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return self._default_system_prompt()
    
    def _default_system_prompt(self) -> str:
        return """You are HC Agent, a self-evolving AI assistant with hierarchical memory.

You reason step-by-step using the ReAct framework:
<think>Your reasoning about what to do next</think>
Then call a tool, or provide:
<answer>Your final answer</answer>

Available tools are provided in the tool list. Always think before acting.
Store useful knowledge for future reference using memory_op tool."""
    
    @staticmethod
    def _extract_tag(text: str, tag: str) -> str:
        """Extract content between XML-style tags."""
        pattern = f"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    def _run_self_reasoning(self, turn_num: int):
        """Run lightweight self-reasoning step."""
        if not self.self_reasoner:
            return
        try:
            state_summary = {
                "total_turns": turn_num,
                "error_count": self.state.error_count,
                "elapsed": time.time() - self.state.start_time,
                "tools_used": {},
            }
            for rec in self.state.turns:
                if rec.tool_name:
                    state_summary["tools_used"][rec.tool_name] =                         state_summary["tools_used"].get(rec.tool_name, 0) + 1
            
            result = self.self_reasoner.reason(
                task=self.state.task,
                recent_records=self.state.turns,
                state_summary=state_summary,
            )
            if result:
                log.info(f"[Loop] Self-reason: progress={result.progress[:60]}, "
                         f"stuck={result.stuck}, confidence={result.confidence:.2f}")
                # If stuck, log a warning
                if result.stuck:
                    log.warning(f"[Loop] Agent appears stuck: {result.stuck_reason}")
        except Exception as e:
            log.warning(f"[Loop] Self-reasoning failed: {e}")
    
    def _check_proactive(self, turn_num: int):
        """Check proactive triggers and handle generated tasks."""
        if not self.proactive:
            return
        try:
            state = {
                "total_turns": turn_num,
                "error_count": self.state.error_count,
                "elapsed": time.time() - self.state.start_time,
            }
            new_tasks = self.proactive.check(state)
            if new_tasks:
                for task in new_tasks:
                    log.info(f"[Loop] Proactive trigger: [{task.trigger.value}] {task.description[:80]}")
                    # Store proactive insight in working memory
                    if self.working_memory:
                        self.working_memory.set(
                            f"proactive_{task.id}", task.description,
                            category="insight", importance=task.priority,
                            ttl=600,  # expire in 10 min
                        )
        except Exception as e:
            log.warning(f"[Loop] Proactive check failed: {e}")
    
    def _run_reflection(self, turn_num: int):
        """Run periodic reflection cycle."""
        if not self.reflection:
            return
        log.info(f"[Loop] Running reflection at turn {turn_num}")
        try:
            self.reflection.reflect(self.state.turns, self.store)
        except Exception as e:
            log.warning(f"[Loop] Reflection failed: {e}")
    
    def _build_summary(self, elapsed: float) -> str:
        """Build execution summary."""
        tools_used = {}
        for rec in self.state.turns:
            if rec.tool_name:
                tools_used[rec.tool_name] = tools_used.get(rec.tool_name, 0) + 1
        
        return (
            f"Task: {self.state.task[:80]}\n"
            f"Turns: {len(self.state.turns)}\n"
            f"Tokens: {self.state.total_tokens}\n"
            f"Time: {elapsed:.1f}s\n"
            f"Tools: {tools_used}\n"
            f"Errors: {self.state.error_count}"
        )
