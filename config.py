"""config.py -- HC Agent Configuration Management.

Provides HCConfig (dataclass-based config) and get_config() factory.
Reads LLM credentials from mykey.py first, then falls back to environment variables.

Usage:
    from config import HCConfig, get_config
    cfg = get_config()              # auto-detect from mykey.py + env
    cfg = HCConfig(llm=LlmConfig(provider="deepseek", api_key="sk-..."))  # manual
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from deep_thinker import DeepThinkConfig

log = logging.getLogger("hc_agent.config")


# ──────────────────────────────────────────────
#  Nested config dataclasses
# ──────────────────────────────────────────────

@dataclass
class LlmConfig:
    """LLM provider configuration."""
    provider: str = "mimo"
    api_key: str = ""
    model: str = "mimo-v2.5-pro"
    base_url: str = ""
    context_window: int = 128000
    temperature: float = 1.0
    max_tokens: int = 8192


@dataclass
class MemoryConfig:
    """Memory system configuration."""
    max_items: int = 500
    context_budget: int = 100000
    summary_threshold: int = 0.8
    # CDH budget allocation
    cdh_total_budget: int = 28000
    cdh_working_ratio: float = 0.40
    cdh_skill_ratio: float = 0.25
    cdh_fact_ratio: float = 0.15
    cdh_history_ratio: float = 0.20
    cdh_domain_boost: float = 1.5
    # CSA scoring weights
    csa_alpha: float = 0.50
    csa_beta: float = 0.25
    csa_gamma: float = 0.15
    csa_decay_hours: float = 24.0
    # HCA compression
    hca_compress_threshold: int = 50


@dataclass
class CSAConfig:
    """Context Selection Algorithm weights."""
    keyword_weight: float = 0.4
    recency_weight: float = 0.3
    frequency_weight: float = 0.3


@dataclass
class EvolutionConfig:
    """Evolution system configuration."""
    max_paper_days: int = 30
    min_relevance: float = 0.5
    skill_update_interval: int = 3600
    reflection_interval: int = 1800


@dataclass
class PathsConfig:
    """File paths configuration."""
    state_file: str = "state/hc_agent_state.json"
    memory_dir: str = "memory/"
    log_dir: str = "logs/"


@dataclass
class MCPServer:
    """Single MCP server configuration."""
    name: str = ""
    command: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class MCPConfig:
    """MCP (Model Context Protocol) configuration."""
    enabled: bool = False
    python_command: str = "python"
    startup_timeout: int = 30
    tool_timeout: int = 60
    tools_enabled: List[str] = field(default_factory=list)
    servers: List[MCPServer] = field(default_factory=list)


@dataclass
class AgentConfig:
    """Agent loop tuning parameters."""
    max_turns: int = 30
    max_history_turns: int = 50

@dataclass
class ToolsConfig:
    """Tools configuration."""
    enable_code_run: bool = True
    enable_web_search: bool = True
    enable_shell: bool = False
    enable_browser: bool = False


@dataclass
class ConsoleConfig:
    """Console/frontend configuration."""
    port: int = 8765
    enable_autonomous: bool = False
    autonomous_interval_minutes: int = 30


# ──────────────────────────────────────────────
#  Top-level config
# ──────────────────────────────────────────────

@dataclass
class FallbackModel:
    """Single fallback model configuration."""
    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""


@dataclass
class FallbackConfig:
    """Model fallback configuration (MixinSession-style round-robin)."""
    enabled: bool = False
    max_retries: int = 3
    base_delay: float = 1.5
    spring_back: int = 300
    models: List[FallbackModel] = field(default_factory=list)


@dataclass
class HCConfig:
    """HC Agent top-level configuration."""
    llm: LlmConfig = field(default_factory=LlmConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    csa: CSAConfig = field(default_factory=CSAConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    console: ConsoleConfig = field(default_factory=ConsoleConfig)
    fallback: FallbackConfig = field(default_factory=FallbackConfig)
    deep_think: DeepThinkConfig = field(default_factory=DeepThinkConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    self_evolve: bool = False
    evolve_on_start: bool = False
    log_level: str = "INFO"
    persistence_path: str = "state/hc_agent_state.json"

    def ensure_dirs(self):
        """Create necessary directories."""
        for d in (self.paths.memory_dir, self.paths.log_dir, os.path.dirname(self.paths.state_file)):
            if d:
                os.makedirs(d, exist_ok=True)


# ──────────────────────────────────────────────
#  Provider default URLs
# ──────────────────────────────────────────────

PROVIDER_URLS = {
    "openai":    "https://api.openai.com/v1",
    "deepseek":  "https://api.deepseek.com/v1",
    "claude":    "https://api.anthropic.com/v1",
    "mimo":      "https://token-plan-cn.xiaomimimo.com/v1",
}


def _read_mykey_config() -> Optional[dict]:
    """Read provider_config or environment_config from mykey.py.

    Returns dict with keys: provider, model, apikey, base_url (all str)
    or None if mykey.py is not importable.
    """
    try:
        import mykey

        # 1. Try provider_config first (has explicit apikey)
        cfg = getattr(mykey, "provider_config", None)
        if cfg and cfg.get("apikey", "").strip():
            log.info(f"mykey.py: using provider_config ({cfg.get('provider')})")
            return cfg

        # 2. Fall back to environment_config
        env_cfg = getattr(mykey, "environment_config", None)
        if env_cfg:
            env_key = env_cfg.get("env_key", "HC_API_KEY")
            apikey = os.environ.get(env_key, "")
            fallbacks = env_cfg.get("env_fallbacks", [])
            if not apikey:
                for fb in fallbacks:
                    apikey = os.environ.get(fb, "")
                    if apikey:
                        break
            if apikey:
                env_cfg["apikey"] = apikey
                log.info(f"mykey.py: using environment_config, key from ${env_key}")
                return env_cfg

        log.warning("mykey.py: no valid config found (no apikey in provider_config, "
                    "no env var for environment_config)")

    except ImportError:
        log.info("mykey.py not found, will try environment variables only")
    except Exception as e:
        log.warning(f"Error reading mykey.py: {e}")

    return None


def _build_llm_config(overrides: dict = None) -> LlmConfig:
    """Build LlmConfig from mykey.py, then env vars, then overrides."""
    cfg = _read_mykey_config()

    provider = (cfg or {}).get("provider", "mimo")
    model = (cfg or {}).get("model", "mimo-v2.5-pro")
    apikey = (cfg or {}).get("apikey", "")
    base_url = (cfg or {}).get("base_url", "")

    # Final fallback: HC_API_KEY env var
    if not apikey:
        apikey = os.environ.get("HC_API_KEY", "")

    # Resolve base_url
    if not base_url:
        base_url = PROVIDER_URLS.get(provider.lower(), "")

    llm = LlmConfig(
        provider=provider,
        api_key=apikey,
        model=model,
        base_url=base_url,
        context_window=(cfg or {}).get("context_win", 128000),
    )

    # Apply overrides
    if overrides:
        for k, v in overrides.items():
            if v is not None and hasattr(llm, k):
                setattr(llm, k, v)

    return llm





def _read_fallback_config() -> FallbackConfig:
    """Read fallback_config from mykey.py if present and enabled."""
    try:
        import mykey as _mk
        fb = getattr(_mk, "fallback_config", None)
        if not fb or not fb.get("enabled", False):
            return FallbackConfig()

        raw_models = fb.get("models", [])
        models = []
        for m in raw_models:
            ak = m.get("apikey", "")
            bu = m.get("base_url", "")
            if not bu:
                bu = PROVIDER_URLS.get(m.get("provider", "").lower(), "")
            models.append(FallbackModel(
                provider=m.get("provider", ""),
                model=m.get("model", ""),
                api_key=ak,
                base_url=bu,
            ))

        cfg = FallbackConfig(
            enabled=True,
            max_retries=fb.get("max_retries", 3),
            base_delay=fb.get("base_delay", 1.5),
            spring_back=fb.get("spring_back", 300),
            models=models,
        )
        log.info(f"mykey.py: fallback enabled, {len(cfg.models)} backup models")
        return cfg

    except ImportError:
        return FallbackConfig()
    except Exception as e:
        log.warning(f"Error reading fallback_config: {e}")
        return FallbackConfig()

def get_config(**overrides) -> HCConfig:
    """Build HCConfig with LLM from mykey.py and optional overrides.

    Args:
        **overrides: CLI overrides (e.g. console_port=9000, self_evolve=True)
    """
    llm = _build_llm_config(overrides.pop("llm", None) if isinstance(overrides.get("llm"), dict) else None)

    cfg = HCConfig(
        llm=llm,
        console=ConsoleConfig(
            port=overrides.pop("console_port", 8765),
            enable_autonomous=overrides.pop("enable_autonomous", False),
            autonomous_interval_minutes=overrides.pop("autonomous_interval", 30),
        ),
    )

    # Apply remaining top-level overrides
    for k, v in overrides.items():
        if v is not None and hasattr(cfg, k):
            setattr(cfg, k, v)

    return cfg
