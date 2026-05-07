"""HC Agent Memory System -- CSA + HCA + CDH Architecture

Layers:
  L0: Raw entries (full text, newest)
  L1: Index entries (one-line summaries, fast routing)
  L2: Compressed summaries (key facts)
  L3: Skills/SOPs (structured knowledge)
"""
from .store import MemoryStore, MemoryItem
from .budget import CDHBudgetManager
from .persistence import WorkingMemory, MemoryStorePersistence

__all__ = ["MemoryStore", "MemoryItem", "CDHBudgetManager",
           "WorkingMemory", "MemoryStorePersistence"]
