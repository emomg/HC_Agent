# HC Agent

新一代 AI Agent 框架，具备 **CSA+HCA 混合注意力记忆**、**CDH 上下文预算**、**论文进化系统**和 **10 轮反思引擎**。

## 核心创新

### 1. CSA + HCA 混合注意力记忆
基于 DeepSeek V4 的记忆架构：
- **CSA（上下文语义注意力）**：根据与当前上下文的语义相似度对记忆项评分
- **HCA（历史上下文注意力）**：根据时间衰减、访问频率和跨会话持久性评分
- **混合评分** = w_csa × CSA + w_hca × HCA，支持动态权重调优

### 2. CDH 上下文预算分配器
- **字符域启发式（Character-Domain Heuristic）**：在记忆域间分配上下文窗口预算
- 公式：`budget_i = total × (relevance^a × recency^b × importance^c) / sum(scores)`
- 根据任务类型和表现自适应调整域权重

### 3. 论文进化系统
- **自动收集**：在失败域搜索相关论文
- **技能升级**：从论文中提取技术，调整技能权重
- **权重调优**：跟踪每个技能域的成功/失败，自适应调整置信度

### 4. 10 轮反思引擎
每 10 轮对话触发：
- **历史压缩**：总结并修剪旧历史
- **技能分析**：识别表现不佳的技能，合并相似技能
- **记忆优化**：提升高价值条目，压缩过期条目

## 项目结构

```
HC-Agent/
├── main.py                    # 入口：CLI 参数解析 + 启动
├── config.py                  # 配置管理：HCConfig + get_config()
├── mykey.py                   # LLM 密钥配置（纯配置，无代码）
├── hc_agent.py                # 核心协调器：串联所有子系统
├── agent_loop.py              # ReAct 推理循环
├── llm_core.py                # LLM 通信层（流式支持）
├── tools.py                   # 工具注册中心 + 内置工具
├── browser_tool.py            # 浏览器自动化工具（TMWebDriver + simph
│                              # tml 简易解析器 + prompt injection）
├── TMWebDriver.py             # Selenium WebDriver 封装
├── simphtml.py                # 轻量 HTML→文本解析器
├── self_reasoner.py           # 内省推理引擎
├── proactive.py               # 主动任务触发器
├── dynamic_prompt.py          # 动态提示词注入（工具→HuggingFace→默认）
├── assets/
│   └── sys_prompt.txt         # 系统提示词
├── memory/                    # 记忆系统
│   ├── store.py               # 记忆存储（CSA + HCA 评分）
│   ├── budget.py              # CDH 上下文预算分配器
│   ├── index.py               # L1 索引层
│   └── persistence.py         # JSON 文件持久化读写
├── evolution/                 # 进化系统
│   ├── paper_collector.py     # 自动论文收集
│   ├── skill_upgrader.py      # 技能权重升级
│   ├── reflection.py          # 10 轮反思引擎
│   ├── meta_reflection.py     # 元反思
│   ├── failure_tracker.py     # 失败追踪
│   ├── strategy_evolver.py    # 策略进化
│   ├── experience_replay.py   # 经验回放
│   └── autonomous_explorer.py # 自主探索
├── frontends/                 # 用户界面
│   ├── stapp.py               # Streamlit Web UI
│   └── console.py             # Rich 终端界面
└── state/                     # 持久化状态
```

## 快速开始

### 1. 配置 API 密钥

编辑 `mykey.py`，取消注释你要使用的 provider，填入 API Key：

```python
# mykey.py -- 取消注释一个 provider 即可
provider_config = {
    "provider": "mimo",
    "model":    "mimo-v2.5-pro",
    "apikey":   "你的API密钥",
    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
}
```

支持的 Provider：

| Provider   | 默认模型                    | 默认端点                                   |
|------------|---------------------------|--------------------------------------------|
| mimo       | mimo-v2.5-pro             | https://token-plan-cn.xiaomimimo.com/v1    |
| deepseek   | deepseek-chat             | https://api.deepseek.com/v1                |
| openai     | gpt-4o                    | https://api.openai.com/v1                  |
| claude     | claude-sonnet-4-20250514  | https://api.anthropic.com/v1               |
| volcengine_maas | doubao-seed-1.6-250615 | https://ark.cn-beijing.volces.com/api/v3  |

### 2. 安装依赖

```bash
pip install -r requirements.txt  # openai tiktoken pyyaml requests rich
```

### 3. 启动

```bash
# Web UI (Streamlit) -- 推荐交互式使用
python run_streamlit.py           # 默认端口 8501
python run_streamlit.py 8502      # 自定义端口

# 终端 CLI
python main.py

# Windows 快捷启动
HC_Agent.bat

# 单次任务模式
python main.py --task "帮我分析最新的 AI 论文"

# 启用自进化 + 启动时触发进化
python main.py --self-evolve --evolve-on-start
```

## 架构概览

```
用户输入 → main.py → HCAgent.__init__()
                        ├── MemoryStore (记忆存储 + CSA/HCA 评分)
                        ├── CDHBudgetManager (CDH 预算管理)
                        ├── L1Index (快速索引)
                        ├── LLMCore (LLM 通信 + 流式)
                        ├── ToolRegistry (工具路由)
                        └── Evolution (进化系统)
                             ├── PaperCollector (论文收集)
                             ├── SkillUpgrader (技能升级)
                             ├── ReflectionEngine (10 轮反思)
                             └── MetaReflection (元反思)
用户输入 → AgentLoop → [思考] → [行动(调用工具)] → [观察] → 循环
```

## 配置说明

### config.py 配置项

| 配置块      | 字段               | 默认值         | 说明                      |
|------------|--------------------|--------------|-----------------------------|
| llm        | provider           | mimo         | LLM 提供商                  |
| llm        | model              | mimo-v2.5-pro | 模型名称                   |
| llm        | context_window     | 128000       | 上下文窗口大小               |
| memory     | max_items          | 500          | 记忆条目上限                 |
| memory     | context_budget     | 100000       | 上下文预算 (token)           |
| csa        | keyword_weight     | 0.4          | 关键词匹配权重               |
| csa        | recency_weight     | 0.3          | 时间近度权重                 |
| csa        | frequency_weight   | 0.3          | 频率权重                     |
| evolution  | max_paper_days     | 30           | 论文收集时间窗口 (天)        |
| evolution  | min_relevance      | 0.5          | 最低相关度阈值               |
| console    | port               | 8765         | 前端端口                     |
| mcp        | enabled            | false        | 是否启用 MCP 协议            |

### 环境变量

| 变量名              | 说明                     |
|---------------------|--------------------------|
| HC_API_KEY          | 通用 API 密钥回退         |
| DEEPSEEK_API_KEY    | DeepSeek 专用密钥         |
| OPENAI_API_KEY      | OpenAI 专用密钥           |

## CLI 参数

```
python main.py [选项]

选项:
  --task "任务描述"           单次任务模式
  --evolve                   触发进化周期
  --self-evolve              启用自主进化（持续运行）
  --reflection               触发反思周期
  --meta-reflect             触发元反思
  --discover                 触发论文发现
  --evolve-on-start          启动时自动触发进化
  --no-save                  不保存状态
```

## 许可证

MIT License
