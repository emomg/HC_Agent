"""Character-Domain Heuristic (CDH) — Context Budget Allocator.

Manages how memory items are allocated into a finite context window.

Formula:
  budget_i = total_budget × (relevance_i^α × recency_i^β × importance_i^γ)
             / Σ_j(relevance_j^α × recency_j^β × importance_j^γ)

Domain match provides a multiplier boost to ensure domain-relevant
items get priority allocation.
"""
from __future__ import annotations
import math, time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import MemoryStore, MemoryItem


@dataclass
class BudgetAllocation:
    """Result of a CDH allocation."""
    working: list       # (MemoryItem, score) for working context
    skills: list        # (MemoryItem, score) for skill/SOP context
    facts: list         # (MemoryItem, score) for factual context
    history: list       # (MemoryItem, score) for history context
    total_tokens: int   # total allocated tokens
    budget_usage: float # fraction of budget used [0,1]


class CDHBudgetManager:
    """Allocate context budget using Character-Domain Heuristic."""
    
    def __init__(self, config=None):
        self.config = config
    
    def allocate(self, query: str, store: "MemoryStore",
                 history_text: str = "",
                 total_budget: int = None) -> BudgetAllocation:
        """Allocate context budget across memory layers.
        
        Args:
            query: Current user query/task
            store: MemoryStore instance
            history_text: Raw history text (treated as working memory)
            total_budget: Override total token budget
        """
        cfg = self.config.memory if self.config else None
        budget = total_budget or (cfg.cdh_total_budget if cfg else 28000)
        
        # Ratios for each section
        r_working = cfg.cdh_working_ratio if cfg else 0.40
        r_skill   = cfg.cdh_skill_ratio   if cfg else 0.25
        r_fact    = cfg.cdh_fact_ratio     if cfg else 0.15
        r_history = cfg.cdh_history_ratio  if cfg else 0.20
        domain_boost = cfg.cdh_domain_boost if cfg else 1.5
        
        # Calculate token budgets per section
        tok_working = int(budget * r_working)
        tok_skill   = int(budget * r_skill)
        tok_fact    = int(budget * r_fact)
        tok_history = int(budget * r_history)
        
        # Score all items
        scored = []
        for item in store.items.values():
            base_score = store.csa_score(query, item)
            # Domain boost
            if item.domain and item.domain.lower() in query.lower():
                base_score *= domain_boost
            scored.append((item, base_score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Allocate by layer with budget constraints
        working = self._fill_budget(scored, [0], tok_working)
        skills  = self._fill_budget(scored, [3], tok_skill)
        facts   = self._fill_budget(scored, [1, 2], tok_fact)
        
        # History is special: just use raw text with truncation
        hist_items = []
        hist_tokens = 0
        if history_text:
            # Truncate history to fit budget
            estimated = len(history_text) // 4  # rough token estimate
            if estimated > tok_history:
                # Keep most recent portion
                chars_budget = tok_history * 4
                history_text = "...\n" + history_text[-chars_budget:]
            hist_items = [(None, history_text)]  # placeholder
            hist_tokens = len(history_text) // 4
        
        # Recalculate remaining budget for overflow
        used = sum(it.token_estimate for it, _ in working)
        used += sum(it.token_estimate for it, _ in skills)
        used += sum(it.token_estimate for it, _ in facts)
        used += hist_tokens
        
        return BudgetAllocation(
            working=working,
            skills=skills,
            facts=facts,
            history=hist_items,
            total_tokens=used,
            budget_usage=min(used / budget, 1.0),
        )
    
    def _fill_budget(self, scored: list, layers: list[int],
                     token_budget: int) -> list:
        """Select items from given layers that fit within token budget."""
        result = []
        used = 0
        for item, score in scored:
            if item.layer not in layers:
                continue
            tok = item.token_estimate
            if used + tok <= token_budget:
                result.append((item, score))
                used += tok
        return result
    
    def format_context(self, alloc: BudgetAllocation) -> str:
        """Format allocation into a context string for LLM injection."""
        sections = []
        
        # L3 Skills
        if alloc.skills:
            lines = []
            for item, score in alloc.skills:
                lines.append(f"  [{item.domain}] {item.content}")
            sections.append("[Skills & SOPs]\n" + "\n".join(lines))
        
        # L1/L2 Facts
        if alloc.facts:
            lines = []
            for item, score in alloc.facts:
                prefix = "IDX" if item.layer == 1 else "SUM"
                lines.append(f"  [{prefix}] {item.content}")
            sections.append("[Knowledge Facts]\n" + "\n".join(lines))
        
        # Working memory (L0)
        if alloc.working:
            lines = []
            for item, score in alloc.working[:10]:  # cap working items
                lines.append(f"  {item.content[:200]}")
            sections.append("[Working Memory]\n" + "\n".join(lines))
        
        return "\n\n".join(sections)
