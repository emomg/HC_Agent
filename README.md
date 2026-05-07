# HC Agent

A next-generation AI agent framework featuring **CSA+HCA Hybrid Attention Memory**, **CDH Context Budget**, **Paper Evolution System**, and **10-turn Reflection Engine**.

## Core Innovations

### 1. CSA + HCA Hybrid Attention Memory
Based on DeepSeek V4's memory architecture:
- **CSA (Contextual Semantic Attention)**: Scores memory relevance based on semantic similarity to current context
- **HCA (Historical Context Attention)**: Scores based on temporal decay, access frequency, and cross-session persistence
- **Hybrid Score** = w_csa * CSA + w_hca * HCA, with dynamic weight tuning

### 2. CDH Context Budget Allocator
- **Character-Domain Heuristic**: Allocates context window budget across memory domains
- Formula: `budget_i = total * (relevance^a * recency^b * importance^c) / sum(scores)`
- Adapts domain weights based on task type and performance

### 3. Paper Evolution System
- **Auto-Collect**: Searches for relevant papers on failure domains
- **Skill Upgrade**: Extracts techniques from papers, adjusts skill weights
- **Weight Tuning**: Tracks success/failure per skill domain, adapts confidence

### 4. 10-Turn Reflection Engine
Every 10 conversation turns:
- **History Compression**: Summarizes and prunes old history
- **Skill Analysis**: Identifies underperforming skills, merges similar ones
- **Memory Optimization**: Boosts high-value items, compresses stale ones

## Architecture

```
HC-Agent/
├── main.py                    # Entry point: CLI args + startup
├── config.py                  # Configuration: HCConfig + get_config()
├── mykey.py                   # LLM credential config (pure config, no code)
├── hc_agent.py                # Core orchestrator: wires all subsystems
├── agent_loop.py              # ReAct reasoning loop
├── llm_core.py                # LLM communication layer (streaming)
├── tools.py                   # Tool registry + built-in tools
├── self_reasoner.py           # Self-reasoning module
├── proactive.py               # Proactive behavior triggers
├── dynamic_prompt.py          # Dynamic prompt builder
├── browser_tool.py            # Browser automation tool
├── simphtml.py                # Lightweight HTML parser
├── TMWebDriver.py             # WebDriver integration for browser tool
├── run_streamlit.py           # Streamlit launcher script
├── HC_Agent.bat               # Windows quick-start batch
├── requirements.txt           # Python dependencies
├── assets/
│   └── sys_prompt.txt         # System prompt
├── memory/                    # Memory system
│   ├── store.py               # Memory store (CSA + HCA scoring)
│   ├── budget.py              # CDH context budget allocator
│   ├── index.py               # L1 index layer
│   └── persistence.py         # Memory persistence layer
├── evolution/                 # Evolution system
│   ├── paper_collector.py     # Auto paper collection
│   ├── skill_upgrader.py      # Skill weight upgrading
│   ├── reflection.py          # 10-turn reflection engine
│   ├── meta_reflection.py     # Meta-reflection
│   ├── failure_tracker.py     # Failure tracking
│   ├── strategy_evolver.py    # Strategy evolution
│   ├── experience_replay.py   # Experience replay
│   └── autonomous_explorer.py # Autonomous exploration
├── frontends/                 # User-facing interfaces
│   ├── stapp.py               # Streamlit Web UI
│   └── console.py             # Rich terminal interface
└── state/                     # Persisted state
```

## Quick Start

### 1. Configure API Key

Edit `mykey.py`, uncomment your provider and fill in the API key:

```python
# mykey.py -- uncomment one provider
provider_config = {
    "provider": "mimo",
    "model":    "mimo-v2.5-pro",
    "apikey":   "your-api-key",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
}
```

Supported providers:

| Provider   | Default Model              | Default Endpoint                          |
|------------|----------------------------|-------------------------------------------|
| mimo       | mimo-v2.5-pro             | https://token-plan-cn.xiaomimimo.com/v1   |
| deepseek   | deepseek-chat             | https://api.deepseek.com/v1               |
| openai     | gpt-4o                    | https://api.openai.com/v1                 |
| claude     | claude-sonnet-4-20250514  | https://api.anthropic.com/v1              |
| volcengine_maas | doubao-seed-1.6-250615 | https://ark.cn-beijing.volces.com/api/v3 |

### 2. Install Dependencies

```bash
pip install -r requirements.txt  # openai tiktoken pyyaml requests rich
```

### 3. Launch

```bash
# Web UI (Streamlit) -- recommended for interactive use
python run_streamlit.py           # default port 8501
python run_streamlit.py 8502      # custom port

# Terminal CLI
python main.py

# Windows quick-start
HC_Agent.bat

# Single task mode
python main.py --task "Analyze this codebase"

# Enable self-evolution + trigger on startup
python main.py --self-evolve --evolve-on-start
```

## Configuration

### config.py Fields

| Section    | Field             | Default   | Description                              |
|------------|-------------------|-----------|------------------------------------------|
| llm        | provider          | mimo      | LLM provider                             |
| llm        | model             | mimo-v2.5-pro | Model name                          |
| llm        | context_window    | 128000    | Context window size                      |
| memory     | max_items         | 500       | Max memory items                         |
| memory     | context_budget    | 100000    | Context budget (tokens)                  |
| csa        | keyword_weight    | 0.4       | Keyword match weight                     |
| csa        | recency_weight    | 0.3       | Recency weight                           |
| csa        | frequency_weight  | 0.3       | Frequency weight                         |
| evolution  | max_paper_days    | 30        | Paper collection window (days)           |
| evolution  | min_relevance     | 0.5       | Minimum relevance threshold              |
| console    | port              | 8765      | Frontend port                            |
| mcp        | enabled           | false     | Enable MCP protocol                      |

### Environment Variables

| Variable           | Description                   |
|--------------------|-------------------------------|
| HC_API_KEY         | Universal API key fallback    |
| DEEPSEEK_API_KEY   | DeepSeek specific key         |
| OPENAI_API_KEY     | OpenAI specific key           |

## CLI Options

```
python main.py [options]

Options:
  --task "description"        Single task mode
  --evolve                    Trigger evolution cycle
  --self-evolve               Enable autonomous evolution (continuous)
  --reflection                Trigger reflection cycle
  --meta-reflect              Trigger meta-reflection
  --discover                  Trigger paper discovery
  --evolve-on-start           Auto-trigger evolution on startup
  --no-save                   Don't save state
```

## License

MIT License
