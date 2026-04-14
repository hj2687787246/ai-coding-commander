# 长期运行 Agent 工作台说明

更新时间：2026-04-11

这份文档只解释当前仓库怎样长期稳定地运行，不替代 `commander/core/任命.md`，也不重写现有指挥官手册。

它当前的边界要明确理解为：

- 这是指挥官系统的外圈工作台文档
- 不是指挥官系统本体
- 不负责定义指挥官身份、长期记忆和任务生命周期真相源

## 1. 这份工作台说明解决什么

当前仓库已经有：

- 指挥官体系
- 阶段文档
- 工程脚本
- 交接说明

本轮补的是一层更瘦的“工作台说明”：

- 让新执行窗口知道先读什么
- 让任务发放和结果回收用固定模板
- 让本地自检入口统一
- 让工程操作不再散落在聊天里

一句话说：

这里吸收了 harness 的思路，但没有复制 `plans / memory / reports / debt` 那整套仓库骨架。

再补一句：

这里也不承担“谁是指挥官、当前主线任务是什么、最近完成了什么”这类本体职责；这些仍以指挥官文档体系为准。

## 2. 当前工作流怎么跑

当前推荐链路是：

1. 指挥官窗口判断目标、边界和验证标准
2. 指挥官窗口按固定模板发给执行窗口
3. 执行窗口按模板读文件、实施改动、跑验证、提交 git
4. 执行窗口按固定顺序汇报结果
5. 指挥官窗口根据结果判断：
   - 已收口
   - 部分完成
   - 阻塞待决策
6. 需要长期保留的内容再写回现有文档体系

这个流程和当前仓库的指挥官体系兼容，关系是：

- `commander/core/任命.md` 负责“谁来指挥、按什么规则工作”
- `commander/outer/agent_workbench.md` 负责“执行工作台现在有哪些固定资产可直接复用”

如果后续继续收拢系统，优先保持这个边界：

- 指挥官文档体系收身份、真相源、生命周期
- 工作台文档收模板、脚本、工程入口
- 不把工作台重新长成第二套指挥官手册

## 3. 哪些资产属于长期记忆

当前仓库已有、且应持续复用的长期记忆资产主要是：

- `commander/core/任命.md`
- `commander/core/主文档.md`
- `commander/state/当前任务卡.md`
- `commander/outer/新窗口交接说明.md`
- `docs/项目沉淀文档.md`
- `docs/项目分阶段实施方案.md`

这些文档负责保留稳定事实、任务状态和交接规则。

本轮新增但不与之平行冲突的资产是：

- `AGENTS.md`
- `commander/outer/agent_workbench.md`
- `commander/outer/指挥官调度原则.md`
- `commander/outer/指挥官harness-v1实施优先级.md`
- `docs/runbook.md`
- `commander/transport/prompts/execution_window_task_template.md`
- `commander/transport/prompts/execution_window_report_template.md`
- `scripts/self_check.ps1`

它们解决的是入口、模板、工程操作和本地验证，不承担第二套长期记忆职责。

其中：

- `commander/outer/指挥官调度原则.md` 负责解释“为什么当前系统需要 harness 的手脚层，以及这层手脚该按什么边界实现”
- `commander/outer/指挥官harness-v1实施优先级.md` 负责解释“如果要真正落第一版 transport，应按什么顺序推进，先做什么、暂时不做什么”

## 4. 任务发放用什么模板

固定模板放在：

- `commander/transport/prompts/execution_window_task_template.md`
- `commander/transport/prompts/execution_window_report_template.md`

其中：

- 任务模板负责固定项目路径、UTF-8 初始化、编码安全规则、必读文件、任务边界、验证项、git 规则、汇报顺序
- 结果模板负责把“改了什么、为什么、验证了什么、是否提交 git、还有什么风险”压成稳定结构

这两个模板不是通用模板，而是直接对齐当前仓库的执行方式。

## 5. 本地自检入口有哪些

推荐入口分两层：

- 最常用本地入口：`scripts/self_check.ps1`
- 阶段性交付入口：`scripts/run_delivery_checks.py`

当前建议心智模型是：

- 日常落地改动，先跑 `self_check.ps1`
- 需要贴近现有阶段交付脚本，再跑 `run_delivery_checks.py`
- 需要更重验证时，再补回归、e2e 或 integration

## 6. 工程操作看哪里

工程操作统一看：

- `docs/runbook.md`

它负责收口：

- 本地最小启动前置
- MySQL / Redis / Alembic / `init_storage.py` 常用路径
- 常用验证命令
- e2e / integration 跑法
- 常见排障入口
- CI 基线入口

存储工程化的细节背景仍以 `docs/storage_engineering_setup.md` 为准；`runbook.md` 负责工程操作，不重复抄一遍原文。

## 7. 执行窗口的最低要求

执行窗口默认要做到：

- 先按 UTF-8 规则初始化 PowerShell
- 涉及中文脚本写入时遵守编码安全规则
- 明确只做本轮任务，不扩写下阶段
- 改完先验证，再汇报
- 有实际改动且验证通过时，默认整理并提交 git

如果结果无法验证，默认不能算“已收口”。
