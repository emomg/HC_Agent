"""Paper Collector — Searches for relevant papers and extracts actionable knowledge.

Workflow:
  1. Given a topic/domain, search for papers via web
  2. Extract key findings, techniques, and formulas
  3. Convert findings into memory items (L2) and potential skills (L3)
  4. Score relevance and importance for skill upgrade decisions
"""
from __future__ import annotations
import json, re, time, logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools import ToolRegistry
    from memory.store import MemoryStore

log = logging.getLogger("hc.evolution.collector")


@dataclass
class Paper:
    """Represents a discovered paper or resource."""
    title: str
    url: str = ""
    abstract: str = ""
    key_findings: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    domain: str = ""
    collected_at: float = field(default_factory=time.time)


class PaperCollector:
    """Collects papers and extracts knowledge for skill evolution."""
    
    def __init__(self, tools: "ToolRegistry", store: "MemoryStore"):
        self.tools = tools
        self.store = store
        self.papers: list[Paper] = []
    
    def collect(self, topic: str, domain: str = "", max_papers: int = 5) -> list[Paper]:
        """Search and collect papers on a given topic.
        
        Args:
            topic: Research topic or question
            domain: Knowledge domain (e.g., "python", "math")
            max_papers: Maximum papers to collect
            
        Returns:
            List of collected Paper objects
        """
        log.info(f"[Collector] Searching papers on: {topic}")
        
        # Search for papers
        search_queries = [
            f"{topic} research paper techniques",
            f"{topic} state of the art methods",
            f"{topic} best practices guide",
        ]
        
        all_results = []
        for query in search_queries:
            result = self.tools.execute("web_search", {"query": query, "num": 5},
                                        {"memory_store": self.store})
            try:
                items = json.loads(result)
                if isinstance(items, list):
                    all_results.extend(items)
            except json.JSONDecodeError:
                continue
        
        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)
        
        # Create Paper objects
        papers = []
        for r in unique_results[:max_papers]:
            paper = Paper(
                title=r.get("title", "Unknown"),
                url=r.get("url", ""),
                domain=domain or self._infer_domain(topic),
            )
            papers.append(paper)
        
        # Extract knowledge from each paper
        for paper in papers:
            self._extract_knowledge(paper)
            self._score_relevance(paper, topic)
        
        self.papers.extend(papers)
        log.info(f"[Collector] Collected {len(papers)} papers on {topic}")
        return papers
    
    def _extract_knowledge(self, paper: Paper):
        """Extract key findings and techniques from a paper."""
        # Use LLM to extract structured knowledge
        # For now, use keyword-based extraction
        if not paper.abstract:
            return
        
        # Extract sentences that look like findings
        sentences = re.split(r'[.!?]', paper.abstract)
        for s in sentences:
            s = s.strip()
            if len(s) < 20:
                continue
            # Heuristics for key findings
            if any(kw in s.lower() for kw in ["we propose", "our method", "achieve", "improve", "result", "show"]):
                paper.key_findings.append(s)
            if any(kw in s.lower() for kw in ["technique", "approach", "algorithm", "method", "framework"]):
                paper.techniques.append(s)
    
    def _score_relevance(self, paper: Paper, topic: str):
        """Score paper relevance to the topic."""
        topic_words = set(topic.lower().split())
        text = (paper.title + " " + paper.abstract).lower()
        
        # Simple keyword overlap scoring
        matches = sum(1 for w in topic_words if w in text)
        paper.relevance_score = matches / max(len(topic_words), 1)
    
    def _infer_domain(self, topic: str) -> str:
        """Infer domain from topic keywords."""
        domain_keywords = {
            "python": ["python", "pip", "django", "flask", "pandas"],
            "math": ["math", "linear algebra", "calculus", "statistics", "probability"],
            "ml": ["machine learning", "neural", "deep learning", "model", "training"],
            "web": ["web", "html", "css", "javascript", "api", "http"],
            "system": ["system", "os", "linux", "process", "memory"],
            "agent": ["agent", "tool", "reasoning", "planning", "autonomous"],
        }
        topic_lower = topic.lower()
        for domain, keywords in domain_keywords.items():
            if any(kw in topic_lower for kw in keywords):
                return domain
        return "general"
    
    def store_findings(self, papers: list[Paper] = None):
        """Store collected paper findings as memory items."""
        papers = papers or self.papers
        stored = 0
        for paper in papers:
            for finding in paper.key_findings:
                self.store.add(
                    finding, layer=2, domain=paper.domain,
                    source=f"paper:{paper.title[:50]}", importance=0.5,
                    tags=["paper_finding"],
                )
                stored += 1
            for technique in paper.techniques:
                self.store.add(
                    technique, layer=2, domain=paper.domain,
                    source=f"paper:{paper.title[:50]}", importance=0.6,
                    tags=["technique"],
                )
                stored += 1
        log.info(f"[Collector] Stored {stored} findings from {len(papers)} papers")
        return stored
    
    def get_upgrade_candidates(self, min_relevance: float = 0.3) -> list[dict]:
        """Get findings that could become skills."""
        candidates = []
        for paper in self.papers:
            if paper.relevance_score < min_relevance:
                continue
            for technique in paper.techniques:
                candidates.append({
                    "content": technique,
                    "domain": paper.domain,
                    "relevance": paper.relevance_score,
                    "source": paper.title,
                })
        return sorted(candidates, key=lambda x: x["relevance"], reverse=True)
