"""Memory Store with CSA (Contextual Semantic Attention) and HCA (Hierarchical Compression Attention).

CSA: Scores memory items by contextual relevance using keyword TF-IDF + recency decay + frequency boost.
HCA: Compresses old items through L0→L1→L2→L3 hierarchical layers.

Reference: Inspired by DeepSeek V4 hybrid attention mechanisms.
"""
from __future__ import annotations
import re, time, math, hashlib
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


@dataclass
class MemoryItem:
    """A single memory entry with metadata for attention scoring."""
    id: str
    content: str
    layer: int = 0                    # 0=raw, 1=index, 2=summary, 3=skill
    tags: list[str] = field(default_factory=list)
    domain: str = ""                  # knowledge domain (e.g. "python", "math")
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    source: str = ""                  # origin (e.g. "user", "tool", "paper")
    importance: float = 0.5           # [0,1] user/importance score
    
    def touch(self):
        """Update access metadata."""
        self.last_accessed = time.time()
        self.access_count += 1
    
    @property
    def age_hours(self) -> float:
        return (time.time() - self.created_at) / 3600.0
    
    @property
    def token_estimate(self) -> int:
        """Rough token count (1 token ≈ 4 chars for English, ~2 chars for Chinese)."""
        cjk = len(re.findall(r'[\u4e00-\u9fff]', self.content))
        latin = len(self.content) - cjk
        return cjk + latin // 4
    
    @staticmethod
    def make_id(content: str) -> str:
        return hashlib.md5(content[:200].encode()).hexdigest()[:12]


def extract_keywords(text: str, top_k: int = 15) -> list[str]:
    """Extract keywords from text using frequency-based scoring."""
    # Remove common stop words and short tokens
    stop = {'the','a','an','is','are','was','were','be','been','being',
            'have','has','had','do','does','did','will','would','shall',
            'should','may','might','can','could','this','that','these',
            'those','it','its','i','me','my','we','our','you','your',
            'he','him','his','she','her','they','them','their','what',
            'which','who','when','where','how','not','no','nor','but',
            'if','then','else','for','to','of','in','on','at','by',
            'with','from','up','out','so','as','and','or','the',
            '的','了','是','在','不','我','有','这','他','她','它',
            '们','你','们','就','都','而','及','与','或','如果',
            '但是','因为','所以','可以','这个','那个','什么','怎么'}
    
    # Tokenize: split by whitespace and punctuation, keep CJK chars
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z_]\w{2,}', text.lower())
    freq = Counter(t for t in tokens if t not in stop and len(t) > 1)
    return [w for w, _ in freq.most_common(top_k)]


class MemoryStore:
    """Unified memory store with CSA + HCA architecture."""
    
    def __init__(self, config=None):
        self.items: dict[str, MemoryItem] = {}
        self.config = config
        self._global_keywords: Counter = Counter()  # corpus-level IDF proxy
    
    def add(self, content: str, layer: int = 0, tags: list[str] = None,
            domain: str = "", source: str = "", importance: float = 0.5) -> MemoryItem:
        """Add a new memory item."""
        item = MemoryItem(
            id=MemoryItem.make_id(content),
            content=content,
            layer=layer,
            tags=tags or [],
            domain=domain,
            source=source,
            importance=importance,
        )
        # Update global keyword counts
        for kw in extract_keywords(content):
            self._global_keywords[kw] += 1
        self.items[item.id] = item
        return item
    
    def get(self, item_id: str) -> Optional[MemoryItem]:
        if item_id in self.items:
            self.items[item_id].touch()
            return self.items[item_id]
        return None
    
    def remove(self, item_id: str) -> bool:
        return self.items.pop(item_id, None) is not None
    
    # ── CSA: Contextual Semantic Attention ──────────────────────────
    
    def csa_score(self, query: str, item: MemoryItem) -> float:
        """Score a memory item's relevance to the current query.
        
        CSA = α·keyword_relevance + β·recency + γ·frequency + δ·importance
        where α+β+γ+δ ≈ 1.0
        """
        cfg = self.config.memory if self.config else None
        alpha = cfg.csa_alpha if cfg else 0.50
        beta  = cfg.csa_beta  if cfg else 0.25
        gamma = cfg.csa_gamma if cfg else 0.15
        delta = 0.10  # importance weight
        
        # 1. Keyword relevance (TF-IDF proxy)
        query_kws = set(extract_keywords(query))
        item_kws  = set(extract_keywords(item.content))
        if query_kws and item_kws:
            overlap = query_kws & item_kws
            # IDF-like: rarer keywords get higher weight
            total = len(self.items) + 1
            idf_score = sum(
                1.0 / (1.0 + math.log(1 + self._global_keywords.get(k, 0)))
                for k in overlap
            )
            max_idf = sum(
                1.0 / (1.0 + math.log(1 + self._global_keywords.get(k, 0)))
                for k in query_kws
            )
            kw_relevance = idf_score / max_idf if max_idf > 0 else 0
        else:
            kw_relevance = 0.0
        
        # 2. Recency (exponential decay)
        decay_h = cfg.csa_decay_hours if cfg else 24.0
        recency = math.exp(-item.age_hours / decay_h)
        
        # 3. Frequency boost (log scale)
        freq = math.log(1 + item.access_count) / math.log(1 + 20)  # normalize to ~1.0 at 20 accesses
        freq = min(freq, 1.0)
        
        # 4. Importance
        imp = item.importance
        
        score = alpha * kw_relevance + beta * recency + gamma * freq + delta * imp
        return round(score, 6)
    
    def csa_rank(self, query: str, layer: int = None, top_k: int = 10) -> list[tuple[MemoryItem, float]]:
        """Rank items by CSA score. Optionally filter by layer."""
        candidates = self.items.values()
        if layer is not None:
            candidates = [i for i in candidates if i.layer == layer]
        scored = [(item, self.csa_score(query, item)) for item in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
    
    # ── HCA: Hierarchical Compression Attention ─────────────────────
    
    def hca_compress(self, llm_fn=None) -> list[str]:
        """Compress old items from higher layers to lower layers.
        
        Strategy:
        - L0 (raw): When > threshold, oldest items → L1 (index summary)
        - L1 (index): When > threshold, oldest items → L2 (compressed summary)
        - L2 (summary): When > threshold, oldest items → L3 (skill/SOP)
        
        Args:
            llm_fn: Optional callable for LLM-based summarization.
                    If None, uses rule-based extraction.
        """
        cfg = self.config.memory if self.config else None
        threshold = cfg.hca_compress_threshold if cfg else 50
        
        actions = []
        
        for layer in range(3):  # L0→L1, L1→L2, L2→L3
            items_in_layer = sorted(
                [i for i in self.items.values() if i.layer == layer],
                key=lambda x: x.created_at
            )
            if len(items_in_layer) <= threshold:
                continue
            
            # Compress oldest items
            to_compress = items_in_layer[:len(items_in_layer) - threshold // 2]
            
            if layer == 0:
                # L0→L1: Create one-line index entries
                for item in to_compress:
                    summary = self._make_index_summary(item)
                    self.add(summary, layer=1, tags=item.tags,
                            domain=item.domain, source="hca:L0→L1",
                            importance=item.importance * 0.8)
                    self.remove(item.id)
                    actions.append(f"L0→L1: {item.id}")
                    
            elif layer == 1:
                # L1→L2: Merge into compressed summaries
                groups = self._group_by_domain(to_compress)
                for domain, group_items in groups.items():
                    merged = self._merge_summaries(group_items, llm_fn)
                    self.add(merged, layer=2, domain=domain,
                            source="hca:L1→L2", importance=0.4)
                    for item in group_items:
                        self.remove(item.id)
                    actions.append(f"L1→L2: {len(group_items)} items → {domain}")
                    
            elif layer == 2:
                # L2→L3: Extract as skills/SOPs
                for item in to_compress:
                    skill = self._extract_skill(item, llm_fn)
                    self.add(skill, layer=3, tags=item.tags,
                            domain=item.domain, source="hca:L2→L3",
                            importance=0.3)
                    self.remove(item.id)
                    actions.append(f"L2→L3: {item.id}")
        
        return actions
    
    def _make_index_summary(self, item: MemoryItem) -> str:
        """Create a one-line index summary from a raw entry."""
        content = item.content.strip()
        # Take first sentence or first 80 chars
        first_line = content.split('\n')[0][:80]
        if len(content) > 80:
            first_line += "..."
        return f"[{item.domain or 'general'}] {first_line}"
    
    def _group_by_domain(self, items: list[MemoryItem]) -> dict[str, list[MemoryItem]]:
        groups = {}
        for item in items:
            d = item.domain or "general"
            groups.setdefault(d, []).append(item)
        return groups
    
    def _merge_summaries(self, items: list[MemoryItem], llm_fn=None) -> str:
        """Merge multiple index entries into a compressed summary."""
        if llm_fn:
            combined = "\n".join(i.content for i in items)
            prompt = f"Compress these notes into 2-3 key facts:\n{combined}"
            return llm_fn(prompt)
        # Rule-based fallback: take unique sentences
        seen = set()
        lines = []
        for item in items:
            for sent in re.split(r'[.。\n]', item.content):
                sent = sent.strip()
                if sent and sent not in seen and len(sent) > 5:
                    seen.add(sent)
                    lines.append(sent)
        return " | ".join(lines[:5])
    
    def _extract_skill(self, item: MemoryItem, llm_fn=None) -> str:
        """Extract a reusable skill/SOP from a compressed summary."""
        if llm_fn:
            prompt = f"Extract a reusable skill/SOP from:\n{item.content}"
            return llm_fn(prompt)
        return f"SOP[{item.domain}]: {item.content[:200]}"
    
    # ── Utility Methods ─────────────────────────────────────────────
    
    def get_all(self) -> list[MemoryItem]:
        """Return all memory items as a list (used by web UI)."""
        return list(self.items.values())
    
    def get_by_layer(self, layer: int) -> list[MemoryItem]:
        return [i for i in self.items.values() if i.layer == layer]
    
    def get_stats(self) -> dict:
        """Get memory statistics."""
        by_layer = {}
        for item in self.items.values():
            by_layer.setdefault(item.layer, 0)
            by_layer[item.layer] += 1
        total_tokens = sum(i.token_estimate for i in self.items.values())
        return {
            "total_items": len(self.items),
            "by_layer": by_layer,
            "total_tokens": total_tokens,
            "global_keywords": len(self._global_keywords),
        }
    
    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "items": {k: {
                "id": v.id, "content": v.content, "layer": v.layer,
                "tags": v.tags, "domain": v.domain,
                "created_at": v.created_at, "last_accessed": v.last_accessed,
                "access_count": v.access_count, "source": v.source,
                "importance": v.importance,
            } for k, v in self.items.items()},
            "global_keywords": dict(self._global_keywords.most_common(500)),
        }
    
    def load_dict(self, data: dict):
        """Deserialize from persistence."""
        self.items.clear()
        for k, v in data.get("items", {}).items():
            self.items[k] = MemoryItem(**v)
        self._global_keywords = Counter(data.get("global_keywords", {}))
