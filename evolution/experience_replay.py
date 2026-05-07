"""Experience Replay Buffer -- Stores and retrieves past experiences.

Inspired by reinforcement learning's experience replay:
  1. Store successful/failed action sequences
  2. Retrieve similar experiences when facing similar problems
  3. Use past experience to guide current decisions
  4. Periodically replay and consolidate important experiences

Enables the agent to "remember" what worked before
and avoid repeating past mistakes.
"""
from __future__ import annotations
import json, time, logging, hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from memory.store import MemoryStore

log = logging.getLogger("hc.evolution.experience_replay")


@dataclass
class Experience:
    """A stored experience episode."""
    experience_id: str
    task_summary: str          # What was the task
    strategy_used: str         # What approach was taken
    tools_used: list[str]      # Which tools were used
    outcome: str               # success/failure/partial
    key_decisions: list[str]   # Important decisions made
    lessons: list[str]         # What was learned
    domain: str = "general"
    difficulty: float = 0.5    # 0.0-1.0
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    replay_count: int = 0
    usefulness: float = 0.5    # Updated based on retrieval feedback


@dataclass
class RetrievalQuery:
    """Query for retrieving similar experiences."""
    task_description: str = ""
    domain: str = ""
    tools_involved: list[str] = field(default_factory=list)
    max_results: int = 5
    min_usefulness: float = 0.3


class ExperienceReplayBuffer:
    """Manages a buffer of past experiences for learning and retrieval.
    
    Usage:
        buffer = ExperienceReplayBuffer(store, max_size=500)
        buffer.store_experience(experience)
        similar = buffer.retrieve(query)
        buffer.consolidate()
    """
    
    def __init__(self, store: "MemoryStore", max_size: int = 500):
        self.store = store
        self.max_size = max_size
        self.experiences: dict[str, Experience] = {}
        self._keyword_index: dict[str, list[str]] = {}  # keyword -> experience_ids
    
    def store_experience(self, task_summary: str, strategy: str, tools: list[str],
                         outcome: str, decisions: list[str], lessons: list[str],
                         domain: str = "general", tags: list[str] = None) -> str:
        """Store a new experience.
        
        Returns:
            experience_id
        """
        exp_id = f"exp_{hashlib.md5(f'{task_summary}{time.time()}'.encode()).hexdigest()[:12]}"
        
        exp = Experience(
            experience_id=exp_id,
            task_summary=task_summary,
            strategy_used=strategy,
            tools_used=tools,
            outcome=outcome,
            key_decisions=decisions,
            lessons=lessons,
            domain=domain,
            tags=tags or [],
        )
        
        self.experiences[exp_id] = exp
        self._index_experience(exp)
        
        # Enforce max size (evict least useful)
        if len(self.experiences) > self.max_size:
            self._evict_least_useful()
        
        # Store in memory system
        self.store.add(
            f"[EXPERIENCE] {task_summary[:100]} -> {outcome}: {'; '.join(lessons[:3])}",
            layer=2, domain=domain,
            source="experience_replay",
            importance=0.6 if outcome == "success" else 0.4,
            tags=["experience", outcome] + (tags or []),
        )
        
        log.info(f"[ExperienceReplay] Stored {exp_id}: {outcome}")
        return exp_id
    
    def retrieve(self, query: RetrievalQuery) -> list[Experience]:
        """Retrieve experiences similar to the query.
        
        Returns experiences ranked by relevance.
        """
        candidates: list[tuple[float, Experience]] = []
        
        for exp in self.experiences.values():
            if exp.usefulness < query.min_usefulness:
                continue
            
            score = self._compute_similarity(query, exp)
            if score > 0.1:  # Minimum threshold
                candidates.append((score, exp))
        
        # Sort by score descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Update replay count
        results = []
        for score, exp in candidates[:query.max_results]:
            exp.replay_count += 1
            results.append(exp)
        
        return results
    
    def retrieve_for_failure(self, failure_type: str, context: str) -> list[Experience]:
        """Retrieve experiences that might help with a specific failure.
        
        Finds experiences where:
        1. Similar failure was overcome (success after similar error)
        2. The domain matches
        3. Lessons are relevant
        """
        results = []
        
        for exp in self.experiences.values():
            if exp.outcome != "success":
                continue
            
            # Check if lessons mention this type of failure
            for lesson in exp.lessons:
                if failure_type.lower() in lesson.lower():
                    results.append(exp)
                    break
            
            # Check tags
            if failure_type in exp.tags:
                results.append(exp)
        
        return results[:5]
    
    def get_success_patterns(self, domain: str = None) -> list[dict]:
        """Get patterns from successful experiences.
        
        Returns aggregated patterns of what works.
        """
        successes = [
            e for e in self.experiences.values()
            if e.outcome == "success" and (domain is None or e.domain == domain)
        ]
        
        if not successes:
            return []
        
        # Aggregate tool usage patterns
        tool_freq: dict[str, int] = {}
        for exp in successes:
            for tool in exp.tools_used:
                tool_freq[tool] = tool_freq.get(tool, 0) + 1
        
        # Aggregate common lessons
        lesson_freq: dict[str, int] = {}
        for exp in successes:
            for lesson in exp.lessons:
                lesson_freq[lesson] = lesson_freq.get(lesson, 0) + 1
        
        return [
            {
                "tool_patterns": dict(sorted(tool_freq.items(), key=lambda x: x[1], reverse=True)[:5]),
                "common_lessons": dict(sorted(lesson_freq.items(), key=lambda x: x[1], reverse=True)[:5]),
                "sample_size": len(successes),
            }
        ]
    
    def update_usefulness(self, exp_id: str, feedback: float):
        """Update usefulness of an experience based on feedback.
        
        Args:
            exp_id: Experience ID
            feedback: -1.0 (useless) to 1.0 (very useful)
        """
        if exp_id in self.experiences:
            exp = self.experiences[exp_id]
            exp.usefulness = max(0.0, min(1.0, exp.usefulness + feedback * 0.1))
    
    def consolidate(self):
        """Consolidate experiences: merge similar ones, prune low-usefulness."""
        if len(self.experiences) < 2:
            return
        
        # Find and merge very similar experiences
        exp_list = list(self.experiences.values())
        merged = set()
        
        for i in range(len(exp_list)):
            if exp_list[i].experience_id in merged:
                continue
            for j in range(i + 1, len(exp_list)):
                if exp_list[j].experience_id in merged:
                    continue
                
                similarity = self._compute_direct_similarity(exp_list[i], exp_list[j])
                if similarity > 0.8:
                    # Keep the more useful one, merge lessons
                    keep, discard = (
                        (exp_list[i], exp_list[j])
                        if exp_list[i].usefulness >= exp_list[j].usefulness
                        else (exp_list[j], exp_list[i])
                    )
                    keep.lessons = list(set(keep.lessons + discard.lessons))
                    keep.tags = list(set(keep.tags + discard.tags))
                    merged.add(discard.experience_id)
        
        # Remove merged
        for eid in merged:
            del self.experiences[eid]
        
        # Prune low usefulness if over capacity
        if len(self.experiences) > self.max_size * 0.9:
            sorted_exp = sorted(
                self.experiences.values(), key=lambda e: e.usefulness
            )
            to_remove = sorted_exp[:len(sorted_exp) // 10]
            for exp in to_remove:
                del self.experiences[exp.experience_id]
        
        log.info(f"[ExperienceReplay] Consolidated: {len(merged)} merged, "
                 f"{len(self.experiences)} remaining")
    
    def get_buffer_stats(self) -> dict:
        """Get buffer statistics."""
        if not self.experiences:
            return {"size": 0}
        
        outcomes = {}
        for exp in self.experiences.values():
            outcomes[exp.outcome] = outcomes.get(exp.outcome, 0) + 1
        
        return {
            "size": len(self.experiences),
            "max_size": self.max_size,
            "outcome_distribution": outcomes,
            "avg_usefulness": sum(e.usefulness for e in self.experiences.values()) / len(self.experiences),
            "avg_replay_count": sum(e.replay_count for e in self.experiences.values()) / len(self.experiences),
            "domains": list(set(e.domain for e in self.experiences.values())),
        }
    
    # --- Internal Methods ---
    
    def _index_experience(self, exp: Experience):
        """Index experience by keywords for fast retrieval."""
        keywords = set()
        
        # Extract keywords from task summary
        for word in exp.task_summary.lower().split():
            if len(word) > 3:
                keywords.add(word)
        
        # Add tags and domain
        keywords.update(t.lower() for t in exp.tags)
        keywords.add(exp.domain.lower())
        
        # Add tool names
        keywords.update(t.lower() for t in exp.tools_used)
        
        for kw in keywords:
            if kw not in self._keyword_index:
                self._keyword_index[kw] = []
            self._keyword_index[kw].append(exp.experience_id)
    
    def _compute_similarity(self, query: RetrievalQuery, exp: Experience) -> float:
        """Compute similarity between query and experience."""
        score = 0.0
        
        # Domain match
        if query.domain and query.domain == exp.domain:
            score += 0.3
        
        # Tool overlap
        if query.tools_involved:
            overlap = len(set(query.tools_involved) & set(exp.tools_used))
            score += 0.2 * (overlap / max(len(query.tools_involved), 1))
        
        # Keyword similarity
        if query.task_description:
            query_words = set(w.lower() for w in query.task_description.split() if len(w) > 3)
            exp_words = set(w.lower() for w in exp.task_summary.split() if len(w) > 3)
            if query_words and exp_words:
                overlap = len(query_words & exp_words)
                score += 0.5 * (overlap / max(len(query_words), 1))
        
        # Boost by usefulness
        score *= (0.5 + 0.5 * exp.usefulness)
        
        return min(1.0, score)
    
    def _compute_direct_similarity(self, a: Experience, b: Experience) -> float:
        """Compute direct similarity between two experiences."""
        score = 0.0
        
        if a.domain == b.domain:
            score += 0.3
        
        tool_overlap = len(set(a.tools_used) & set(b.tools_used))
        tool_total = max(len(set(a.tools_used) | set(b.tools_used)), 1)
        score += 0.3 * (tool_overlap / tool_total)
        
        words_a = set(w.lower() for w in a.task_summary.split() if len(w) > 3)
        words_b = set(w.lower() for w in b.task_summary.split() if len(w) > 3)
        if words_a and words_b:
            word_overlap = len(words_a & words_b)
            word_total = max(len(words_a | words_b), 1)
            score += 0.4 * (word_overlap / word_total)
        
        return score
    
    def _evict_least_useful(self):
        """Evict the least useful experience."""
        if len(self.experiences) <= self.max_size:
            return
        
        least_useful = min(self.experiences.values(), key=lambda e: e.usefulness)
        del self.experiences[least_useful.experience_id]
        
        # Remove from index
        for kw, ids in self._keyword_index.items():
            if least_useful.experience_id in ids:
                ids.remove(least_useful.experience_id)
        
        log.debug(f"[ExperienceReplay] Evicted {least_useful.experience_id}")


# Alias for import compatibility
ExperienceReplay = ExperienceReplayBuffer
