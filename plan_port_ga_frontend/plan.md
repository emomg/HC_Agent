<!-- EXECUTION PROTOCOL
1. file_read(plan.md)，找到第一个 [ ] 项
2. 该步标注了SOP → file_read 该SOP的速查段
3. 执行该步骤 + Mini验证产出
4. file_patch 标记 [ ] → [x]+简要结果，然后回到步骤1继续下一个 [ ]
5. 所有步骤标记完成后 → 终止检查：file_read(plan.md)确认0个 [ ] 残留
-->

# 移植 GenericAgent 前端+浏览器能力到 HC-Agent

需求：将 GA 的浏览器自动化(TMWebDriver+simphtml)和前端适配层(至少Qt+Web)移植到 HC-Agent
约束：保持 HC 的 ToolRegistry 注册模式；不破坏现有进化/记忆系统；multi_module_integration_sop 防类名不匹配

## 探索发现
- GA 工具层：ga.py 全局函数 + driver(TMWebDriver)单例，前端通过 GeneraticAgent 实例访问 handler/state
- GA 前端接口：_run(task)/_stop()/next_llm()/llmclient/handler/history/task_queue/is_running
- GA agent_loop：generator-based，yield 输出，handler.dispatch() 调工具
- HC 工具层：ToolRegistry 类，register(name,fn,desc,schema)，类方法
- HC 前端：仅 ConsoleFrontend，agent.chat_stream() 或 agent.run_task()
- HC agent_loop：AgentLoop.run() 非 generator，内部调 registry.execute()
- 关键差异：GA 的 agent_runner_loop 是 generator(yield流式)，HC 的 AgentLoop.run() 是同步返回

## 执行计划

### 第一阶段：浏览器能力移植

1. [ ] 复制 TMWebDriver.py + simphtml.py 到 HC 项目根目录
   依赖：无

2. [ ] 新建 browser_tool.py：BrowserTool 类，包装 web_scan/web_execute_js/navigate 等
   接口：ToolRegistry.register(name, fn, desc, schema) 兼容
   内部：import TMWebDriver，管理 driver 单例，调用 simphtml 做 HTML 简化
   依赖：1

3. [ ] 修改 tools.py：注册 BrowserTool 到 ToolRegistry
   在 _register_builtins() 或相关位置添加 browser 工具注册
   依赖：2

4. [ ] 修改 hc_agent.py：_build_tool_registry() 中启用浏览器工具
   添加 config.tools.enable_browser 开关
   依赖：3

### 第二阶段：前端适配层

5. [ ] 扩展 HCAgent 暴露前端所需状态
   添加属性：history(task_queue), llmclient, is_running, stop(), next_llm()
   以及 chat_stream() 的 generator 接口（如 agent_loop 需改造为 generator）
   依赖：无

6. [ ] 新建 frontends/stapp.py：Streamlit Web 前端
   仿 GA 的 stapp2.py(1100行 Streamlit)，实现流式对话 + 工具结果展示
   用户指定用 Streamlit
   依赖：5

7. [ ] 新建 frontends/qtapp.py：Qt GUI 前端
   仿 GA 的 qtapp.py，实现桌面 GUI + 流式显示
   依赖：5

8. [ ] 修改 main.py：添加 --web/--qt 参数选择前端
   依赖：6, 7

### 第三阶段：验证

9. [ ] ast.parse 全部新文件 + import 链验证
   multi_module_integration_sop
   依赖：1-8

10. [ ] 端到端测试：browser tool 调用 + 前端启动
    依赖：9

## 验证检查点
11. [ ] [VERIFY] 启动独立验证 subagent
     SOP: verify_sop.md plan_sop.md
     操作：读 plan_sop.md 第四章 → 准备 verify_context.json → 启动验证 subagent → 读取 VERDICT
