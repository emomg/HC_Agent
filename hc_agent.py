"""HC Agent -- Main orchestrator that ties all components together.

The HC Agent initializes and wires:
  - Memory System (Store + CDH Budget + L1 Index)
  - LLM Core (communication layer)
  - Tool Registry (dynamic tool routing)
  - Agent Loop (ReAct + Inner Monologue)
  - Evolution System (Papers + Skills + Reflection)
  - Frontend (console/CLI interface)

Lifecycle:
  1. Initialize components from config
  2. Load persisted state (if any)
  3. Accept user input -> run agent loop -> return results
  4. Periodic reflection and evolution
  5. Persist state on shutdown

Init order matters: store -> budget -> index -> llm -> tools -> loop -> evolution.
"""
from __future__ import annotations
import json, time, logging, sys
from pathlib import Path
from typing import Optional

from config import HCConfig, get_config
from memory.store import MemoryStore
from memory.budget import CDHBudgetManager
from memory.index import L1Index
from llm_core import LLMCore
from tools import ToolRegistry
from agent_loop import AgentLoop
from evolution.paper_collector import PaperCollector
from evolution.skill_upgrader import SkillUpgrader
from evolution.reflection import ReflectionEngine
from evolution.meta_reflection import MetaReflectionEngine
from evolution.failure_tracker import FailureTracker
from evolution.strategy_evolver import StrategyEvolver
from evolution.experience_replay import ExperienceReplayBuffer
from evolution.autonomous_explorer import AutonomousExplorer
from memory.persistence import MemoryStorePersistence, WorkingMemory
from self_reasoner import SelfReasoner
from dynamic_prompt import DynamicPromptBuilder
from proactive import ProactiveManager
from deep_thinker import DeepThinker

log = logging.getLogger("hc_agent")


class HCAgent:
    """The main HC Agent that coordinates all subsystems."""
    
    def __init__(self, config: HCConfig = None):
        self.config = config or get_config()
        self._setup_logging()
        
        # Core components
        self.store = MemoryStore(config=self.config)
        self.budget_mgr = CDHBudgetManager(config=self.config)
        self.index = L1Index(store=self.store)
        self.llm = LLMCore(config=self.config)
        self.tools = self._build_tool_registry()
        
        # Evolution system
        self.collector = PaperCollector(tools=self.tools, store=self.store)
        self.upgrader = SkillUpgrader(store=self.store, collector=self.collector)
        self.strategy_evolver = StrategyEvolver(store=self.store)
        self.meta_reflection = MetaReflectionEngine(llm=self.llm, store=self.store)
        self.failure_tracker = FailureTracker(store=self.store)
        self.experience_replay = ExperienceReplayBuffer(store=self.store)
        self.autonomous_explorer = AutonomousExplorer(
            store=self.store, execute_fn=None,
        )
        self.reflection = ReflectionEngine(
            store=self.store, upgrader=self.upgrader,
            meta_reflection=self.meta_reflection,
        )
        
        # New: Persistence + Working Memory
        data_dir = Path(self.config.paths.memory_dir) if hasattr(self.config, 'paths') and self.config.paths else Path("data")
        self.persistence = MemoryStorePersistence(str(data_dir))
        self.persistence.install(self.store)
        self.working_memory = WorkingMemory(data_dir)
        
        # New: Self-reasoning, Dynamic prompt, Proactive
        self.self_reasoner = SelfReasoner(self.llm, self.working_memory)
        self.dynamic_prompt = DynamicPromptBuilder(
            base_prompt_path=str(Path(self.config.paths.memory_dir).parent / "sys_prompt.txt") if hasattr(self.config, 'paths') else None,
        )
        self.proactive = ProactiveManager(working_memory=self.working_memory)
        self.deep_thinker = DeepThinker(
            llm=self.llm,
            config=self.config.deep_think,
        )
        
        # Agent loop
        self.loop = AgentLoop(
            config=self.config, llm=self.llm, tools=self.tools,
            store=self.store, budget_mgr=self.budget_mgr,
            reflection_engine=self.reflection,
            failure_tracker=self.failure_tracker,
            experience_replay=self.experience_replay,
            working_memory=self.working_memory,
            self_reasoner=self.self_reasoner,
            dynamic_prompt=self.dynamic_prompt,
            proactive=self.proactive,
            persistence=self.persistence,
            deep_thinker=self.deep_thinker,
        )
        
        # State
        self.session_count = 0
        self.total_turns = 0
        
        log.info("[HCAgent] Initialized with all subsystems")
    
    def _setup_logging(self):
        """Configure logging."""
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    
    def _build_tool_registry(self) -> ToolRegistry:
        """Build and register all tools."""
        registry = ToolRegistry()
        
        # Optional: browser tools (web_scan, web_execute_js)
        if self.config.tools.enable_browser:
            try:
                from browser_tool import register_browser_tools
                register_browser_tools(registry)
                log.info("[HCAgent] Browser tools registered")
            except Exception as e:
                log.warning(f"[HCAgent] Browser tools not available: {e}")
        
        return registry
    
    def run_task(self, task: str, max_turns: int = None) -> str:
        """Execute a single task through the agent loop.
        
        Args:
            task: Natural language task description
            max_turns: Override max turns for this task
            
        Returns:
            Final answer string
        """
        self.session_count += 1
        log.info(f"[HCAgent] Session #{self.session_count}: {task[:80]}...")
        
        answer = self.loop.run(task, max_turns=max_turns)
        self.total_turns += len(self.loop.state.turns)
        
        # Post-task: index new memories
        self.index.index_domain_keys()
        
        return answer
    
    def interactive(self):
        """Run in interactive console mode."""
        print(self._banner())
        
        while True:
            try:
                user_input = input("\n🧑 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Goodbye!")
                break
            
            if not user_input:
                continue
            
            if user_input.lower() in ("quit", "exit", "q"):
                print("👋 Goodbye!")
                break
            
            if user_input.lower() == "status":
                self._print_status()
                continue
            
            if user_input.lower() == "stats":
                self._print_memory_stats()
                continue
            
            if user_input.lower().startswith("evolve "):
                topic = user_input[7:].strip()
                self._evolve(topic)
                continue
            
            # Run task
            answer = self.run_task(user_input)
            print(f"\n🤖 Agent: {answer}")
    
    def _banner(self) -> str:
        """Print welcome banner."""
        return f"""
╔══════════════════════════════════════════════════╗
║              🧠 HC Agent v1.0                    ║
║  Hierarchical Compressed Agent                   ║
║  CSA + HCA + CDH Memory System                   ║
╚══════════════════════════════════════════════════╝
  Model: {self.config.llm.model}
  Context Budget: {self.config.memory.context_budget} chars
  Max Turns: {self.config.agent.max_turns}
  
  Commands: status | stats | evolve <topic> | quit
"""
    
    def _print_status(self):
        """Print current agent status."""
        print(f"""
📊 Agent Status:
  Sessions: {self.session_count}
  Total Turns: {self.total_turns}
  Memory Items: {len(self.store.items)}
  Reflection Cycles: {self.reflection.reflection_count}
  Skills: {len(self.store.get_by_layer(layer=3))}
""")
    
    def _print_memory_stats(self):
        """Print memory statistics."""
        stats = self.index.stats()
        domain_dist = self.budget_mgr.domain_distribution()
        print(f"""
🧠 Memory Stats:
  Total Items: {stats['total']}
  By Layer: {stats['by_layer']}
  By Domain: {stats['by_domain']}
  
📐 Domain Distribution (CDH):
  {json.dumps(domain_dist, indent=2)}
  
📉 CSA Weights: α={self.config.csa.keyword_weight}, β={self.config.csa.recency_weight}, γ={self.config.csa.frequency_weight}
""")
    
    def _evolve(self, topic: str):
        """Trigger full evolution: paper collection + skill upgrading + strategy evolution + meta-reflection + autonomous exploration."""
        print(f"🔬 Evolving skills for: {topic}")
        
        # 1. Paper-based skill evolution
        results = self.upgrader.upgrade_from_papers(topic)
        print(f"  ✅ Skill evolution: {len(results)} updates")
        for r in results[:5]:
            print(f"    - {r}")
        
        # 2. Strategy evolution via meta-reflection
        strategy_update = self.strategy_evolver.evolve(topic)
        if strategy_update:
            print(f"  ✅ Strategy evolved: {len(strategy_update.get('changes', []))} changes")
        
        # 3. Meta-reflection on evolution effectiveness
        meta = self.meta_reflection.reflect_on_evolution(
            evolution_topic=topic,
            current_system_prompt=self.config.evolution.strategy_system_prompt,
        )
        if meta:
            print(f"  ✅ Meta-reflection: {len(meta.get('insights', []))} insights")
        
        # 4. Autonomous exploration
        exploration = self.autonomous_explorer.explore()
        if exploration:
            print(f"  ✅ Autonomous exploration: {len(exploration)} discoveries")
        
        # 5. Failure pattern analysis
        failure_report = self.failure_tracker.get_failure_report()
        if failure_report.get("total_failures", 0) > 0:
            print(f"  📊 Failure report: {failure_report['total_failures']} failures tracked")
        
        print(f"✅ Evolution cycle complete for: {topic}")
    
    def save_state(self, path: str = None):
        """Persist agent state to disk."""
        path = path or self.config.persistence_path
        state = {
            "version": "1.0",
            "timestamp": time.time(),
            "session_count": self.session_count,
            "total_turns": self.total_turns,
            "memory": self.store.serialize(),
            "reflection_count": self.reflection.reflection_count,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        log.info(f"[HCAgent] State saved to {path}")
    
    def load_state(self, path: str = None):
        """Load persisted state from disk."""
        path = path or self.config.persistence_path
        if not Path(path).exists():
            log.info(f"[HCAgent] No saved state found at {path}")
            return False
        
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        
        self.session_count = state.get("session_count", 0)
        self.total_turns = state.get("total_turns", 0)
        self.store.deserialize(state.get("memory", {}))
        self.reflection.reflection_count = state.get("reflection_count", 0)
        
        log.info(f"[HCAgent] State loaded from {path}: {len(self.store.items)} items")
        return True
    
    # ── Streamlit frontend interface ──────────────────────────────
    def get_status(self) -> dict:
        """Return current agent status for the web UI."""
        return {
            "turn": self.total_turns,
            "session_count": self.session_count,
            "memory_count": len(self.store.items),
            "skill_count": len(self.store.get_by_layer(layer=3)),
            "model": self.config.llm.model,
        }
    
    def chat_stream(self, prompt: str):
        """Run a task and yield result chunks for Streamlit streaming.
        
        Since LLMCore does not implement true SSE streaming yet,
        this delegates to run_task() and yields the full response.
        The Streamlit _stream_worker drains this generator into a queue.
        """
        try:
            result = self.loop.run(prompt)
            # Yield in small chunks for smoother UI rendering
            for i in range(0, len(result), 200):
                yield result[i:i+200]
        except Exception as e:
            yield f"[Error] {e}"
