"""Skill Upgrader — Upgrades skills based on paper findings and usage patterns.

Skill Lifecycle:
  1. Discovery: New technique found in paper or experience
  2. Creation: Store as L3 skill with initial confidence
  3. Usage: Confidence increases with successful use
  4. Upgrade: Merge new knowledge into existing skill
  5. Pruning: Remove low-confidence unused skills

Weight Formula:
  new_weight = old_weight * decay + usage_bonus + paper_boost
"""
from __future__ import annotations
import json, time, logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.store import MemoryStore
    from evolution.paper_collector import PaperCollector

log = logging.getLogger("hc.evolution.upgrader")


class SkillUpgrader:
    """Manages skill lifecycle and upgrades."""
    
    USAGE_BOOST = 0.05      # confidence boost per successful use
    PAPER_BOOST = 0.1       # confidence boost from paper validation
    DECAY_RATE = 0.995      # confidence decay per day of non-use
    MERGE_THRESHOLD = 0.7   # similarity threshold for merging
    PRUNE_THRESHOLD = 0.1   # minimum confidence to keep skill
    
    def __init__(self, store: "MemoryStore", collector: "PaperCollector" = None):
        self.store = store
        self.collector = collector
    
    def upgrade_from_papers(self, topic: str, domain: str = "") -> list[str]:
        """Upgrade skills based on paper findings.
        
        Steps:
          1. Collect papers on topic
          2. Extract upgrade candidates
          3. For each candidate, try to merge into existing skill or create new
        """
        if not self.collector:
            log.warning("[Upgrader] No paper collector available")
            return []
        
        # Collect papers
        papers = self.collector.collect(topic, domain=domain)
        self.collector.store_findings(papers)
        
        # Get upgrade candidates
        candidates = self.collector.get_upgrade_candidates()
        
        upgraded = []
        for cand in candidates:
            existing = self._find_similar_skill(cand["content"], cand["domain"])
            if existing:
                self._merge_skill(existing, cand)
                upgraded.append(f"Merged into {existing.id}")
            else:
                skill = self._create_skill(cand)
                upgraded.append(f"Created {skill.id}")
        
        log.info(f"[Upgrader] {len(upgraded)} skills upgraded for topic: {topic}")
        return upgraded
    
    def upgrade_from_experience(self, successful_approach: str, domain: str = "") -> str:
        """Upgrade or create skill based on successful experience."""
        existing = self._find_similar_skill(successful_approach, domain)
        if existing:
            existing.importance = min(existing.importance + self.USAGE_BOOST, 1.0)
            existing.access_count += 1
            existing.touch()
            return f"Boosted {existing.id} to {existing.importance:.2f}"
        else:
            skill = self._create_skill({
                "content": successful_approach,
                "domain": domain,
                "relevance": 0.5,
                "source": "experience",
            })
            return f"Created {skill.id}"
    
    def record_usage(self, skill_id: str, success: bool):
        """Record a skill usage event."""
        item = self.store.items.get(skill_id)
        if not item:
            return
        item.touch()
        if success:
            item.importance = min(item.importance + self.USAGE_BOOST, 1.0)
        else:
            item.importance = max(item.importance - self.USAGE_BOOST * 0.5, 0.0)
    
    def apply_decay(self):
        """Apply time-based decay to all skills."""
        now = time.time()
        day_seconds = 86400
        decayed = 0
        for item in self.store.get_by_layer(layer=3):
            days_idle = (now - item.last_accessed) / day_seconds
            if days_idle > 1:
                factor = self.DECAY_RATE ** days_idle
                old_imp = item.importance
                item.importance *= factor
                if old_imp != item.importance:
                    decayed += 1
        log.info(f"[Upgrader] Decayed {decayed} idle skills")
        return decayed
    
    def prune_skills(self) -> list[str]:
        """Remove skills below confidence threshold."""
        to_remove = []
        for item in self.store.get_by_layer(layer=3):
            if item.importance < self.PRUNE_THRESHOLD:
                to_remove.append(item.id)
        
        for skill_id in to_remove:
            self.store.remove(skill_id)
        
        if to_remove:
            log.info(f"[Upgrader] Pruned {len(to_remove)} low-confidence skills")
        return to_remove
    
    def merge_similar(self) -> list[str]:
        """Find and merge similar skills."""
        skills = self.store.get_by_layer(layer=3)
        if len(skills) < 2:
            return []
        
        merged = []
        seen = set()
        for i, s1 in enumerate(skills):
            if s1.id in seen:
                continue
            for s2 in skills[i+1:]:
                if s2.id in seen:
                    continue
                # Simple keyword overlap for similarity
                words1 = set(s1.content.lower().split())
                words2 = set(s2.content.lower().split())
                overlap = len(words1 & words2) / max(len(words1 | words2), 1)
                if overlap > self.MERGE_THRESHOLD:
                    # Merge into the higher-importance one
                    primary = s1 if s1.importance >= s2.importance else s2
                    secondary = s2 if primary is s1 else s1
                    primary.content += f"\n- {secondary.content}"
                    primary.importance = max(primary.importance, secondary.importance)
                    primary.touch()
                    self.store.remove(secondary.id)
                    seen.add(secondary.id)
                    merged.append(f"Merged {secondary.id} into {primary.id}")
        
        return merged
    
    def _find_similar_skill(self, content: str, domain: str):
        """Find existing skill similar to given content."""
        ranked = self.store.csa_rank(content, layer=3, top_k=3)
        if ranked:
            best_item, best_score = ranked[0]
            if best_score > 0.2:
                return best_item
        return None
    
    def _create_skill(self, candidate: dict):
        """Create a new skill from candidate."""
        return self.store.add(
            candidate["content"],
            layer=3,
            domain=candidate.get("domain", "general"),
            source=candidate.get("source", "upgrader"),
            importance=min(candidate.get("relevance", 0.5), 0.8),
        )
    
    def _merge_skill(self, existing, candidate: dict):
        """Merge candidate knowledge into existing skill."""
        new_info = candidate["content"]
        if new_info not in existing.content:
            existing.content += f"\n- {new_info}"
        existing.importance = min(
            existing.importance + self.PAPER_BOOST * candidate.get("relevance", 0.5),
            1.0
        )
        existing.touch()
