"""L1 Index Layer — Library Catalog System.

The L1 index is like a library's directory desk: you don't walk
to the shelves, you check the catalog to know exactly where your
book is. It's tiny (a few hundred tokens) but enables fast routing
to any knowledge in the store.

Structure:
  - Each entry is a one-line summary with domain tag
  - Entries are grouped by domain for fast lookup
  - The index can be injected as a compact routing table
"""
from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import MemoryStore, MemoryItem


class L1Index:
    """L1 Index — compact knowledge routing table."""
    
    def __init__(self, store: "MemoryStore"):
        self.store = store
    
    def build_index(self) -> str:
        """Build a compact index string from L1 items.
        
        Returns a formatted string like:
          [python] → ga.py has 1892 lines, tools schema, agent loop
          [math] → linear algebra basics, matrix operations
          [web] → browser control via TMWebDriver
        """
        l1_items = self.store.get_by_layer(layer=1)
        if not l1_items:
            return "[No indexed knowledge yet]"
        
        # Group by domain
        by_domain: dict[str, list[str]] = defaultdict(list)
        for item in l1_items:
            domain = item.domain or "general"
            by_domain[domain].append(item.content[:100])
        
        # Format as compact catalog
        lines = []
        for domain in sorted(by_domain.keys()):
            entries = by_domain[domain]
            summary = " | ".join(entries[:5])  # max 5 per domain
            if len(entries) > 5:
                summary += f" (+{len(entries)-5} more)"
            lines.append(f"  [{domain}] → {summary}")
        
        return f"[Knowledge Index — {len(l1_items)} entries]\n" + "\n".join(lines)
    
    def build_skill_index(self) -> str:
        """Build index specifically for L3 skills."""
        l3_items = self.store.get_by_layer(layer=3)
        if not l3_items:
            return "[No skills registered]"
        
        lines = []
        for item in l3_items:
            lines.append(f"  [{item.domain}] {item.content[:120]}")
        return f"[Skill Index — {len(l3_items)} skills]\n" + "\n".join(lines)
    
    def search(self, query: str, top_k: int = 5) -> list["MemoryItem"]:
        """Fast search through L1 index using CSA ranking."""
        ranked = self.store.csa_rank(query, layer=1, top_k=top_k)
        return [item for item, score in ranked]
    
    def route(self, query: str) -> dict[str, float]:
        """Route query to relevant domains with confidence scores.
        
        Returns: {domain: relevance_score}
        """
        ranked = self.store.csa_rank(query, top_k=20)
        domain_scores: dict[str, float] = defaultdict(float)
        for item, score in ranked:
            d = item.domain or "general"
            domain_scores[d] += score
        
        # Normalize
        total = sum(domain_scores.values()) or 1.0
        return {d: round(s / total, 4) for d, s in domain_scores.items()}
