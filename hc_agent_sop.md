# HC Agent -- Usage & Development SOP

## Quick Start
```bash
cd D:\桌面\HC-Agent
python mykey.py set deepseek          # store your API key (interactive prompt)
python main.py                         # interactive console
python main.py --task "do X"           # single task mode
```

## API Key Management
- `python mykey.py set <provider>` -- store key (interactive)
- `python mykey.py set <provider> --value sk-xxx` -- store from value
- `python mykey.py set <provider> --file key.txt` -- store from file
- `python mykey.py ls` -- list stored keys
- `python mykey.py del <provider>` -- delete a key
- Keys stored in `~/.hc_keys.enc` (XOR obfuscation, not crypto-safe)
- Resolution order: explicit param > stored key > env var (HC_API_KEY, DEEPSEEK_API_KEY, etc.)

## Project Structure
```
HC-Agent/
  main.py           -- CLI entry point (argparse)
  hc_agent.py       -- Main orchestrator (wires all components)
  config.py         -- Config dataclasses (AgentConfig/LLMConfig/...)
  llm_core.py       -- LLM communication layer (OpenAI/Claude compatible)
  agent_loop.py     -- ReAct loop with Inner Monologue
  tools.py          -- Dynamic tool registry
  mykey.py          -- API key manager (CLI + importable)
  evolution/        -- Self-evolution subsystem
    paper_collector.py    -- Arxiv paper fetching
    skill_upgrader.py     -- Skill extraction from papers
    reflection.py         -- Self-reflection on failures
    meta_reflection.py    -- Meta-reflection on evolution effectiveness
    failure_tracker.py    -- Failure pattern tracking
    strategy_evolver.py   -- Strategy mutation/optimization
    experience_replay.py  -- Experience buffer (ranked replay)
    autonomous_explorer.py -- Autonomous task exploration
  memory/           -- Memory subsystem
    store.py        -- MemoryStore (item CRUD)
    budget.py       -- CDH budget allocation (keyword/recency/frequency)
    index.py        -- L1 fast-access index
  frontends/
    console.py      -- Console REPL frontend
```

## Config Flow
1. `main.py` creates `AgentConfig()` (defaults from dataclasses)
2. Env overrides: `HC_PROVIDER`, `HC_API_KEY`, `HC_BASE_URL`, `HC_MODEL`
3. JSON config file: `python main.py --config path.json`
4. `config.ensure_dirs()` creates required directories
5. Passed to `HCAgent(config)` which wires all components

## Development Rules
- **Import chain**: Always verify `python -c "import hc_agent"` after changes
- **Class aliases**: config.py exports `HCConfig=Config=get_config` for compatibility
- **Add comments**: Every new module needs module docstring + key function docstrings
- **Evolution modules**: Each evolution/*.py class must be importable from evolution/__init__.py

## Evolution CLI
```bash
python main.py --evolve              # paper collection + skill extraction
python main.py --reflection          # reflect on recent failures
python main.py --meta-reflect        # meta-reflection on evolution effectiveness
python main.py --failures            # show failure pattern report
python main.py --explore             # autonomous exploration
python main.py --topic "LLM agents"  # specify topic for evolve/explore
```

## Troubleshooting
- **ImportError on startup**: Run `python -c "import hc_agent"` to find broken import
- **Key not found**: Check `python mykey.py ls` and env vars
- **Class name mismatch**: Check evolution/__init__.py imports match actual class names (add aliases if needed)
