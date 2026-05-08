# ══════════════════════════════════════════════════════════════════════════════
#  HC-Agent — mykey.py 配置模板（复制为 mykey.py 后填入真实凭证）
# ══════════════════════════════════════════════════════════════════════════════
#
#  ┌─────────────────────────────────────────────────────────────────────────┐
#  │ 快速上手：只需 3 步                                                      │
#  │  1. 把本文件复制为 mykey.py（如果还没有的话）                              │
#  │  2. 在下面的"推荐最优配置"区域取消注释一个 provider，填入你的 apikey       │
#  │  3. 运行 python main.py                                                │
#  └─────────────────────────────────────────────────────────────────────────┘
#
#  ────────── 配置加载流程 ──────────
#
#  config.py 会 import 本文件，读取变量名含 'config' 的条目：
#
#      变量名                              → 用途
#      ─────────────────────────────────────────────────────────────────────
#      provider_config                     → ★ LLM 主配置（active provider）
#      deepseek_config / openai_config ... → 预存的其他 provider（config.py 按名加载）
#      environment_config                  → 环境变量回退（当 mykey.py 无 provider_config 时）
#      proxy                               → 全局 HTTP 代理
#
#  启动优先级：命令行参数 > provider_config > environment_config > 报错
#
#  ────────── Provider 命名约定 ──────────
#
#  变量名建议用 {provider}_config 格式，方便 config.py 的 get_provider_config(name)
#  按名查找。活跃配置固定使用 provider_config，config.py 默认读它。
#
#  你也可以在命令行覆盖：
#      python main.py --provider openai --model gpt-4o --api-key sk-xxx
#
#  ────────── provider_config 字段速查 ──────────
#
#  ┌─────────────┬─────────────┬─────────────────────────────────────────────┐
#  │ 字段         │ 是否必填    │ 说明                                       │
#  ├─────────────┼─────────────┼─────────────────────────────────────────────┤
#  │ provider     │ ★ 必填     │ 提供商标识，用于自动匹配 base_url            │
#  │              │             │ 已知: deepseek / openai / claude / mimo     │
#  ├─────────────┼─────────────┼─────────────────────────────────────────────┤
#  │ model        │ ★ 必填     │ 模型名称，原样传给 API                       │
#  ├─────────────┼─────────────┼─────────────────────────────────────────────┤
#  │ apikey       │ ★ 必填     │ 你的 API 密钥                               │
#  │              │             │ sk-ant-* → x-api-key 头                    │
#  │              │             │ 其他      → Authorization: Bearer           │
#  ├─────────────┼─────────────┼─────────────────────────────────────────────┤
#  │ base_url     │ 可选       │ API 端点，留空则按 provider 自动匹配         │
#  │              │             │ deepseek → https://api.deepseek.com/v1     │
#  │              │             │ openai   → https://api.openai.com/v1       │
#  │              │             │ claude   → https://api.anthropic.com/v1    │
#  │              │             │ mimo     → https://token-plan-cn.          │
#  │              │             │            xiaomimimo.com/v1               │
#  ├─────────────┼─────────────┼─────────────────────────────────────────────┤
#  │ context_win  │ 可选       │ 上下文窗口大小（token 数），默认 128000      │
#  │              │             │ 仅作为历史裁剪阈值，不是硬上下文限制          │
#  └─────────────┴─────────────┴─────────────────────────────────────────────┘
#
#  ────────── apibase 自动拼接规则 ──────────
#
#  base_url 会自动补全：
#      'http://host:2001'                      → 补 /v1/chat/completions
#      'http://host:2001/v1'                   → 补 /chat/completions
#      'http://host:2001/v1/chat/completions'  → 原样使用
#
#  ────────── 环境变量回退 ──────────
#
#  当 mykey.py 不存在或无 provider_config 时，config.py 会读环境变量：
#      HC_LLM_PROVIDER   默认 deepseek
#      HC_API_KEY         ★ 必须设置（否则报错）
#      HC_LLM_MODEL       默认 deepseek-chat
#      HC_LLM_BASE_URL    默认空（自动匹配）
#
#  ────────── config.py 自动生成的其他配置 ──────────
#
#  以下配置由 config.py 根据环境自动填充，一般不需要在 mykey.py 中修改：
#
#      paths.state_file          状态文件路径（默认 ./hc_agent_state.json）
#      memory.max_items          最大记忆条目（默认 500）
#      memory.context_budget     上下文预算 token（默认 100000）
#      memory.summary_threshold  摘要触发阈值（默认 40000）
#      csa.*                     CSA 阈值配置
#      evolution.*               进化引擎配置
#      mcp.*                     MCP 工具协议配置
#      console.*                 控制台配置（端口、自主模式等）
#
#  如需覆盖，在 mykey.py 底部定义 environment_config 并设置对应环境变量。
#
# ══════════════════════════════════════════════════════════════════════════════
#  全局 HTTP 代理（所有没有单独指定 proxy 的 session 共用）
# ══════════════════════════════════════════════════════════════════════════════
# proxy = 'http://127.0.0.1:2082'


# ══════════════════════════════════════════════════════════════════════════════
#  ★ 推荐默认配置（取消注释一个即可，优先级从上到下）
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. MiMo (小米) ─ 国内直连，延迟最低 ─────────────────────────────────────
# provider_config = {
#     "provider": "mimo",
#     "model":    "mimo-v2.5-pro",
#     "apikey":   "",
#     "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
#     # "context_win": 128000,
# }

# ── 2. DeepSeek ─ 国产性价比之王 ─────────────────────────────────────────────
# provider_config = {
#     "provider": "deepseek",
#     "model":    "deepseek-chat",
#     "apikey":   "sk-...",
#     "base_url": "",  # 留空使用默认: https://api.deepseek.com/v1
#     # "context_win": 128000,
# }

# ── 3. OpenAI ─ GPT-4o 原生 ──────────────────────────────────────────────────
# provider_config = {
#     "provider": "openai",
#     "model":    "gpt-4o",
#     "apikey":   "sk-...",
#     "base_url": "",  # 留空使用默认: https://api.openai.com/v1
#     # "context_win": 128000,
# }

# ── 4. Claude (Anthropic) ─ 长上下文 ──────────────────────────────────────────
# provider_config = {
#     "provider": "claude",
#     "model":    "claude-sonnet-4-20250514",
#     "apikey":   "sk-ant-...",
#     "base_url": "",  # 留空使用默认: https://api.anthropic.com/v1
#     # "context_win": 128000,
# }

# ── 5. 其他兼容 OpenAI 的 Provider ────────────────────────────────────────────
# provider_config = {
#     "provider": "OpenAI",       # 通用协议标识
#     "model":    "GPT-5.5",
#     "apikey":   "sk-...", 
#     "base_url": "https://api.openai.com/v1",
#     # "context_win": 8000,
# }


# ══════════════════════════════════════════════════════════════════════════════
#  预存 Provider（可选，供 config.py 的 get_provider_config(name) 按名调用）
# ══════════════════════════════════════════════════════════════════════════════
#
# deepseek_config = {
#     "provider": "deepseek",
#     "model":    "deepseek-chat",
#     "apikey":   "sk-...",
#     "base_url": "",
# }
#
# openai_config = {
#     "provider": "openai",
#     "model":    "gpt-4o",
#     "apikey":   "sk-...",
#     "base_url": "",
# }
#
# claude_config = {
#     "provider": "claude",
#     "model":    "claude-sonnet-4-20250514",
#     "apikey":   "sk-ant-...",
#     "base_url": "",
# }


# ══════════════════════════════════════════════════════════════════════════════
#  环境变量配置（可选，当 mykey.py 无 provider_config 时作为回退）
# ══════════════════════════════════════════════════════════════════════════════
#
# environment_config = {
#     "provider":  "HC_LLM_PROVIDER",
#     "model":     "HC_LLM_MODEL",
#     "apikey":    "HC_API_KEY",
#     "base_url":  "HC_LLM_BASE_URL",
# }



# ══════════════════════════════════════════════════════════════════════════════
#  模型自动 Fallback 配置（可选，多模型轮替，主模型失败时自动切换）
# ══════════════════════════════════════════════════════════════════════════════
#
#  工作原理（类似 GenericAgent 的 MixinSession）：
#
#    1. 启动时为主模型（provider_config）+ 后备模型列表各创建一个 LLMCore
#    2. 调用 ask() 时先用主模型，失败后按顺序尝试后备模型
#    3. 全部失败后指数退避重试（base_delay × 2^round）
#    4. 主模型冷却时间过后自动回弹（spring_back）
#
#  启用方式：取消注释下方 fallback_config 并填入你的 API key
#
# ┌──────────────┬──────────┬──────────────────────────────────────────────┐
# │ 字段          │ 默认值   │ 说明                                        │
# ├──────────────┼──────────┼──────────────────────────────────────────────┤
# │ enabled      │ False    │ 是否启用 fallback                            │
# │ max_retries  │ 3        │ 全部模型轮替后最大重试轮数                     │
# │ base_delay   │ 1.5      │ 首轮失败后等待秒数（后续 ×2 递增）             │
# │ spring_back  │ 300      │ 主模型冷却时间（秒），过后自动回弹到主模型      │
# │ models       │ []       │ 后备模型列表，每项同 provider_config 格式      │
# └──────────────┴──────────┴──────────────────────────────────────────────┘
#
#  使用示例（取消注释并填入真实 key 即可启用）：
#
# fallback_config = {
#     "enabled": True,
#     "max_retries": 3,
#     "base_delay": 1.5,
#     "spring_back": 300,
#     "models": [
#         {
#             "provider": "deepseek",
#             "model":    "deepseek-chat",
#             "apikey":   "sk-...",
#             "base_url": "",
#         },
#         {
#             "provider": "openai",
#             "model":    "gpt-4o",
#             "apikey":   "sk-...",
#             "base_url": "",
#         },
#         # 可以继续添加更多后备模型
#     ],
# }
