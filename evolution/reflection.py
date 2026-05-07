"""Reflection Engine — Periodic optimization every 10 turns.

Three-phase reflection cycle:
  Phase 1: History Compression
    - Summarize recent turns into concise notes
    - Extract key decisions and outcomes
    - Store as L2 compressed summaries
    
  Phase 2: Skill Analysis
    - Review skill usage patterns
    - Identify frequently used skills → boost confidence
    - Identify unused skills → apply decay
    - Detect skill gaps → trigger paper collection
    
  Phase 3: Memory Optimization
    - Merge similar memory items
    - Promote frequently accessed L0 items to L1
    - Compress old L1 items to L2
    - Prune low-importance items
"""
from __future__ import annotations
import json, time, logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.store import MemoryStore
    from evolution.skill_upgrader import SkillUpgrader
    from evolution.meta_reflection import MetaReflection
    from agent_loop import TurnRecord

log = logging.getLogger("hc.evolution.reflection")


class ReflectionEngine:
    """Periodic reflection and optimization."""
    
    def __init__(self, store: "MemoryStore", upgrader: "SkillUpgrader" = None,
                 meta_reflection: "MetaReflection" = None):
        self.store = store
        self.upgrader = upgrader
        self.meta_reflection = meta_reflection
        self.reflection_count = 0
    
    def reflect(self, turns: list["TurnRecord"], store: "MemoryStore" = None):
        """Run full reflection cycle.
        
        Called every N turns (typically 10) by the agent loop.
        """
        store = store or self.store
        self.reflection_count += 1
        
        log.info(f"[Reflection] Starting cycle #{self.reflection_count}")
        start = time.time()
        
        # Phase 1: History Compression
        compressed = self._compress_history(turns)
        
        # Phase 2: Skill Analysis
        skill_actions = self._analyze_skills(turns)
        
        # Phase 3: Memory Optimization
        mem_actions = self._optimize_memory(store)
        
        # Phase 4: Meta-Reflection (LLM深度反思)
        meta_report = None
        if self.meta_reflection:
            try:
                meta_report = self.meta_reflection.deep_reflect(
                    turns=turns, context={"reflection_count": self.reflection_count}
                )
                # Process failure reflections
                if meta_report.get("failure_reflections"):
                    for fr in meta_report["failure_reflections"]:
                        if self.meta_reflection.failure_tracker:
                            self.meta_reflection.failure_tracker.track(
                                tool_name=fr.get("tool_name", "unknown"),
                                error_msg=fr.get("failure_type", "unknown"),
                                args={},
                                context={"reflection_generated": True},
                            )
                log.info(f"[Reflection] Meta-reflection completed: "
                         f"{len(meta_report.get('new_strategies', []))} new strategies, "
                         f"{len(meta_report.get('failure_reflections', []))} failure reflections")
            except Exception as e:
                log.warning(f"[Reflection] Meta-reflection failed: {e}")
        
        elapsed = time.time() - start
        log.info(
            f"[Reflection] Cycle #{self.reflection_count} done in {elapsed:.2f}s: "
            f"compressed={compressed}, skills={skill_actions}, memory={mem_actions}"
        )
        
        return {
            "cycle": self.reflection_count,
            "compressed_items": compressed,
            "skill_actions": skill_actions,
            "memory_actions": mem_actions,
            "meta_reflection": meta_report,
        }
    
    def _compress_history(self, turns: list["TurnRecord"]) -> int:
        """Compress recent turn history into concise summaries."""
        if not turns:
            return 0
        
        # Group turns into chunks of 5
        chunk_size = 5
        compressed = 0
        
        for i in range(0, len(turns), chunk_size):
            chunk = turns[i:i + chunk_size]
            
            # Build summary from chunk
            tools_used = []
            key_results = []
            for t in chunk:
                if t.tool_name:
                    tools_used.append(t.tool_name)
                if t.tool_result and len(t.tool_result) > 10:
                    key_results.append(t.tool_result[:100])
                if t.think:
                    key_results.append(t.think[:100])
            
            if not key_results:
                continue
            
            summary = (
                f"Turns {chunk[0].turn}-{chunk[-1].turn}: "
                f"Tools: {', '.join(set(tools_used))}. "
                f"Key: {'; '.join(key_results[:3])}"
            )
            
            # Store as L2 compressed summary
            self.store.add(
                summary, layer=2, domain="reflection",
                source=f"reflection_cycle_{self.reflection_count}",
                importance=0.4, tags=["history_compressed"],
            )
            compressed += 1
        
        return compressed
    
    def _analyze_skills(self, turns: list["TurnRecord"]) -> int:
        """Analyze skill usage patterns and trigger upgrades."""
        actions = 0
        
        if not self.upgrader:
            return actions
        
        # Count tool usage
        tool_counts = {}
        for t in turns:
            if t.tool_name:
                tool_counts[t.tool_name] = tool_counts.get(t.tool_name, 0) + 1
        
        # Record successful tool usages as experience
        for t in turns:
            if t.tool_name and t.tool_result and "error" not in t.tool_result.lower():
                # This was a successful tool use — potential skill
                if t.think and len(t.think) > 50:
                    domain = self._infer_domain_from_tool(t.tool_name)
                    self.upgrader.upgrade_from_experience(
                        f"Approach: {t.think[:200]}", domain=domain
                    )
                    actions += 1
        
        # Apply decay and pruning
        self.upgrader.apply_decay()
        pruned = self.upgrader.prune_skills()
        actions += len(pruned)
        
        # Merge similar skills
        merged = self.upgrader.merge_similar()
        actions += len(merged)
        
        return actions
    
    def _optimize_memory(self, store: "MemoryStore") -> int:
        """Optimize memory: promote, compress, prune."""
        actions = 0
        
        # Promote frequently accessed L0 items to L1
        for item in store.get_by_layer(layer=0):
            if item.access_count >= 3 and item.importance >= 0.5:
                # Promote to L1 index
                store.add(
                    f"[IDX] {item.content[:100]}",
                    layer=1, domain=item.domain,
                    source=f"promoted_from_{item.id}",
                    importance=item.importance,
                    tags=["auto_promoted"],
                )
                actions += 1
        
        # Run HCA compression
        compressed = store.hca_compress()
        actions += len(compressed)
        
        # Prune very old, low-importance L0 items
        threshold = time.time() - 7 * 86400  # 7 days
        to_remove = []
        for item in store.get_by_layer(layer=0):
            if (item.last_accessed < threshold and 
                item.importance < 0.2 and 
                item.access_count < 2):
                to_remove.append(item.id)
        
        for item_id in to_remove[:20]:  # limit pruning
            store.remove(item_id)
            actions += 1
        
        return actions
    
    def _infer_domain_from_tool(self, tool_name: str) -> str:
        """Infer domain from tool name."""
        tool_domains = {
            "code_run": "programming",
            "file_read": "file_ops",
            "file_write": "file_ops",
            "web_search": "research",
            "shell_exec": "system",
        }
        return tool_domains.get(tool_name, "general")
