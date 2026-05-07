"""Evolution System — Paper collection, skill upgrading, reflection, and self-evolution.

Components:
  PaperCollector: Searches for relevant papers and extracts knowledge
  SkillUpgrader: Upgrades skills based on paper findings and usage patterns
  ReflectionEngine: Periodic optimization of history, skills, and memory
  MetaReflection: LLM-driven deep reflection for strategic learning
  FailureTracker: Root cause analysis and anti-pattern library
  StrategyEvolver: Dynamic strategy evolution based on experience
  ExperienceReplay: Experience replay buffer for pattern matching
  AutonomousExplorer: Self-directed learning during idle time
"""
from .paper_collector import PaperCollector
from .skill_upgrader import SkillUpgrader
from .reflection import ReflectionEngine
from .meta_reflection import MetaReflection, ReflectionReport
from .failure_tracker import FailureTracker, FailureRecord
from .strategy_evolver import StrategyEvolver
from .experience_replay import ExperienceReplay, Experience
from .autonomous_explorer import AutonomousExplorer

__all__ = [
    "PaperCollector", "SkillUpgrader", "ReflectionEngine",
    "MetaReflection", "ReflectionReport",
    "FailureTracker", "FailureRecord",
    "StrategyEvolver",
    "ExperienceReplay", "Experience",
    "AutonomousExplorer",
]
