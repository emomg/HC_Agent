<!-- EXECUTION PROTOCOL (每轮必读，这是你的执行指南)
1. file_read(plan.md)，找到第一个 [ ] 项
2. 该步标注了SOP -> file_read 该SOP的速查段
3. 执行该步骤 + Mini验证产出
4. file_patch 标记 [ ] -> [x]+简要结果，然后回到步骤1继续下一个[ ]
5. 所有步骤（包括验证步骤）标记完成后 -> 终止检查：file_read(plan.md)确认0个[ ]残留
禁止凭记忆执行 | 禁止跳过验证步骤 | 禁止未经终止检查就结束 | 禁止停下来输出纯文字汇报
搬砖活（读大量代码/文件/网页/重复操作）优先委托subagent，保持主agent上下文干净
-->
# 增强HC-Agent自进化能力 -- 基于自身架构分析

需求：分析通用Agent自身能力模式，实现5个自进化模块让HC-Agent能通过经验思考自进化
约束：保持向后兼容（增强而非替换现有模块）、模块可独立使用、无额外外部依赖

## 探索发现

- 发现1：现有reflection.py(196行)仅做机械式计数(think_len>50则+0.05)，无LLM驱动的深度反思
- 发现2：agent_loop.py仅计数error_count，3次失败直接放弃，无失败归因和教训提取
- 发现3：system_prompt.txt是静态文件，不随经验变化，无策略进化机制
- 发现4：无经验回放机制，成功/失败案例不被系统性存储和复用
- 发现5：paper_collector.py完全被动等待调用，无自主探索能力
- 发现6：skill_upgrader.py的upgrade_from_experience仅从成功操作提取，不记录失败模式
- 发现7：config.py有HCEvolutionConfig但仅含简单阈值，无策略参数

## 自身架构映射（Agent自身能力 -> HC-Agent应实现）

| 我的能力 | HC-Agent缺失 | 应建模块 |
|---------|-------------|---------|
| working_checkpoint持续追踪 | 无持久化工作记忆 | experience_replay |
| 3次失败升级策略 | 仅计数到3放弃 | failure_tracker |
| thinking块元推理 | 无自我推理 | meta_reflection |
| SOP动态加载执行 | 静态prompt | strategy_evolver |
| 长期记忆更新 | 机械式L1->L2 | experience_replay |
| 先探测再行动 | 被动等调用 | autonomous_explorer |

## 执行计划

1. [x] 创建 evolution/meta_reflection.py -- LLM驱动的深度反思引擎 ✓(342行)
   依赖：无
   内容：调用LLM分析近期交互，提取策略教训、成功模式、失败归因，生成结构化反思报告存入memory

2. [x] 创建 evolution/failure_tracker.py -- 失败归因与反模式库 ✓(307行)
   依赖：无
   内容：记录每次失败的上下文/原因/解决方式，建立反模式库，相似场景命中时提前预警

3. [x] 创建 evolution/strategy_evolver.py -- 动态策略进化器 ✓(313行)
   依赖：步骤1,2
   内容：基于反思报告和失败模式，动态修改system_prompt和推理策略，维护策略版本和A/B对比

4. [x] 创建 evolution/experience_replay.py -- 经验回放缓冲 ✓(348行)区
   依赖：无
   内容：存储关键成功/失败经验（含turn/think/action/result/lesson），支持相似场景检索和策略注入

5. [x] 创建 evolution/autonomous_explorer.py -- 自主探索引擎 ✓(241行)
   依赖：步骤4
   内容：空闲时主动搜集论文、测试新方法、探索未知领域，将发现转化为技能和记忆

6. [x] 修改 evolution/__init__.py -- 导出新模块 ✓(已更新)
   依赖：步骤1-5
   内容：将5个新模块加入evolution包导出

7. [x] 修改 evolution/reflection.py -- 集成meta_reflection ✓(已集成)
   依赖：步骤1
   内容：在现有reflect()流程中插入LLM深度反思阶段，保持原有机械式流程兼容

8. [x] 修改 agent_loop.py -- 集成failure_tracker和experience_replay ✓(已集成)
   依赖：步骤2,4
   内容：在错误处理路径中记录失败，在每轮开始检索相似经验注入context

9. [x] 修改 hc_agent.py -- 注册新模块到主协调器 ✓(已注册)
   依赖：步骤1-8
   内容：在HCAgent.__init__中初始化新模块，在step()循环中集成经验回放和策略进化

10. [x] 修改 config.py -- 新增进化模块配置项 ✓(已添加5个新配置类+AgentConfig字段)
    依赖：无
    内容：新增HCSelfEvolutionConfig（反思频率/失败阈值/探索强度/回放缓冲大小等）

11. [x] 修改 main.py -- 新增命令行参数 ✓(已添加meta-reflect/failures/explore/topic)
    依赖：步骤9
    内容：新增 --explore（启动自主探索）和 --evolve-report（生成进化报告）参数

---

## 验证检查点
12. [x] **[VERIFY] 语法验证和集成测试** ✓(11/11语法PASS, 7/7 import PASS, 顶层3/3 PASS, 修复: MetaReflection别名+ExperienceReplay别名+HCConfig/Config/get_config别名)
     操作：对所有修改/新建的.py文件执行python -c "import ast; ast.parse(open(f).read())"验证语法 | 检查模块间import链无循环依赖 | 检查所有新模块可独立import
     产出：验证报告，列出每个文件的语法检查结果和import关系

---

## 最终状态
所有12步完成，0个[ ]残留。
修复汇总（验证阶段发现并修复）：
- evolution/meta_reflection.py: MetaReflectionEngine -> 别名MetaReflection
- evolution/experience_replay.py: ExperienceReplayBuffer -> 别名ExperienceReplay  
- config.py: AgentConfig -> 别名HCConfig, Config, get_config
