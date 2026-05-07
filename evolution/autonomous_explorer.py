"""Autonomous Explorer -- Self-directed learning during idle time.

When the agent is not actively solving user tasks, this module:
  1. Explores the codebase to understand its own structure
  2. Searches for useful knowledge and patterns
  3. Tests its own capabilities and finds limits
  4. Generates "homework" tasks for self-improvement
  5. Builds a map of what it can and cannot do

Philosophy: The best time to learn is when you're not under pressure.
"""
from __future__ import annotations
import json, time, logging, os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Callable

if TYPE_CHECKING:
    from memory.store import MemoryStore

log = logging.getLogger("hc.evolution.autonomous_explorer")


@dataclass
class ExplorationTask:
    """A self-directed exploration task."""
    task_id: str
    name: str
    description: str
    category: str        # codebase/knowledge/capability/boundary
    priority: float      # 0.0-1.0
    status: str = "pending"  # pending/running/done/failed
    findings: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


@dataclass
class ExplorationReport:
    """Summary of exploration findings."""
    total_tasks: int = 0
    completed: int = 0
    failed: int = 0
    key_findings: list[str] = field(default_factory=list)
    new_capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


class AutonomousExplorer:
    """Manages self-directed exploration and learning.
    
    Usage:
        explorer = AutonomousExplorer(store, execute_fn)
        explorer.queue_exploration_tasks()
        results = explorer.run_pending_tasks(max_tasks=3)
    """
    
    def __init__(self, store: "MemoryStore", execute_fn: Callable = None):
        self.store = store
        self.execute_fn = execute_fn  # Function to run code/tools
        self.tasks: dict[str, ExplorationTask] = {}
        self.findings: list[str] = []
        self._knowledge_map: dict[str, list[str]] = {
            "capabilities": [],
            "limitations": [],
            "tools_understood": [],
            "patterns_learned": [],
        }
    
    def queue_exploration_tasks(self):
        """Generate and queue exploration tasks based on current gaps."""
        # Analyze what we don't know yet
        gaps = self._identify_knowledge_gaps()
        
        for gap in gaps:
            task = ExplorationTask(
                task_id=f"explore_{int(time.time())}_{len(self.tasks)}",
                name=gap["name"],
                description=gap["description"],
                category=gap["category"],
                priority=gap.get("priority", 0.5),
            )
            self.tasks[task.task_id] = task
        
        log.info(f"[Explorer] Queued {len(gaps)} exploration tasks")
        return len(gaps)
    
    def run_pending_tasks(self, max_tasks: int = 3) -> ExplorationReport:
        """Run pending exploration tasks.
        
        Args:
            max_tasks: Maximum number of tasks to run in this batch
            
        Returns:
            ExplorationReport with findings
        """
        pending = [
            t for t in self.tasks.values()
            if t.status == "pending"
        ]
        pending.sort(key=lambda t: t.priority, reverse=True)
        
        report = ExplorationReport(total_tasks=len(pending))
        
        for task in pending[:max_tasks]:
            try:
                task.status = "running"
                findings = self._execute_task(task)
                task.findings = findings
                task.status = "done"
                task.completed_at = time.time()
                report.completed += 1
                report.key_findings.extend(findings)
                
                # Store findings in memory
                for finding in findings:
                    self.store.add(
                        f"[EXPLORATION] {task.name}: {finding}",
                        layer=2, domain=task.category,
                        source="autonomous_explorer",
                        importance=0.5,
                        tags=["exploration", task.category],
                    )
                
                log.info(f"[Explorer] Completed: {task.name}")
                
            except Exception as e:
                task.status = "failed"
                task.findings.append(f"Error: {str(e)}")
                report.failed += 1
                log.warning(f"[Explorer] Failed: {task.name}: {e}")
        
        # Update knowledge map
        self._update_knowledge_map(report)
        
        return report
    
    def add_finding(self, category: str, finding: str):
        """Add a finding from external source."""
        self.findings.append(finding)
        if category in self._knowledge_map:
            self._knowledge_map[category].append(finding)
    
    def get_knowledge_map(self) -> dict:
        """Get current knowledge map."""
        return {
            **self._knowledge_map,
            "total_explorations": len([t for t in self.tasks.values() if t.status == "done"]),
            "pending_explorations": len([t for t in self.tasks.values() if t.status == "pending"]),
        }
    
    def generate_self_improvement_tasks(self) -> list[dict]:
        """Generate tasks for self-improvement based on findings."""
        tasks = []
        
        # Check for weak areas
        if len(self._knowledge_map.get("limitations", [])) > 3:
            tasks.append({
                "name": "Address known limitations",
                "description": "Review and address accumulated limitations",
                "priority": 0.8,
                "limitations": self._knowledge_map["limitations"][-5:],
            })
        
        # Check for unexplored patterns
        if len(self._knowledge_map.get("patterns_learned", [])) < 5:
            tasks.append({
                "name": "Learn more interaction patterns",
                "description": "Study successful interaction patterns from experience buffer",
                "priority": 0.6,
            })
        
        return tasks
    
    # --- Internal Methods ---
    
    def _identify_knowledge_gaps(self) -> list[dict]:
        """Identify what we don't know yet."""
        gaps = []
        
        # Codebase exploration
        gaps.append({
            "name": "Understand module dependencies",
            "description": "Map import relationships between all modules",
            "category": "codebase",
            "priority": 0.7,
        })
        
        gaps.append({
            "name": "Analyze error patterns",
            "description": "Review recent errors to find common failure modes",
            "category": "capability",
            "priority": 0.8,
        })
        
        gaps.append({
            "name": "Test tool boundaries",
            "description": "Systematically test each tool's limits and capabilities",
            "category": "boundary",
            "priority": 0.6,
        })
        
        gaps.append({
            "name": "Study successful strategies",
            "description": "Analyze experience buffer for successful patterns",
            "category": "knowledge",
            "priority": 0.7,
        })
        
        return gaps
    
    def _execute_task(self, task: ExplorationTask) -> list[str]:
        """Execute an exploration task and return findings."""
        findings = []
        
        if task.category == "codebase":
            findings.append(f"Module analysis queued: {task.name}")
            
        elif task.category == "capability":
            findings.append(f"Capability assessment queued: {task.name}")
            
        elif task.category == "boundary":
            findings.append(f"Boundary test queued: {task.name}")
            
        elif task.category == "knowledge":
            findings.append(f"Knowledge extraction queued: {task.name}")
        
        return findings if findings else ["Task queued for execution"]
    
    def _update_knowledge_map(self, report: ExplorationReport):
        """Update knowledge map based on exploration results."""
        for finding in report.key_findings:
            self.findings.append(finding)
            
            # Categorize findings
            lower = finding.lower()
            if "can" in lower or "able" in lower or "success" in lower:
                self._knowledge_map["capabilities"].append(finding)
            elif "cannot" in lower or "limit" in lower or "fail" in lower:
                self._knowledge_map["limitations"].append(finding)
            elif "pattern" in lower or "strategy" in lower:
                self._knowledge_map["patterns_learned"].append(finding)
