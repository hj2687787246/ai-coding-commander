# 指挥官调度与结果回收 harness v1

更新时间：2026-04-11

## 9. checkpoint / resume

`checkpoint.json` 只是 transport 的恢复锚点，不是第二套记忆层。它会跟着 `dispatch / ingest / status` 一起刷新，和当前 `status.json` 同步落在：

```text
.runtime/commander/tasks/<task_id>/checkpoint.json
```

最小恢复用法：

```powershell
.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_resume --task-id harness-v1
```

checkpoint 里至少保留：

- `task_id`
- `title`
- `current_phase`
- `recommended_action`
- `recent_trusted_completion`
- `next_minimal_action`
- `blockers`
- `pending_decisions`
- `key_paths`
- `event_count`
- `updated_at`
- `active_subagents`：任务收口前先清零；它只是 transport 护栏，不是第二记忆层。

边界保持不变：

- 它只服务恢复和转运，不替代真实 report
- 它不会自动开窗、不会多 worker 调度、不会引入新的状态机
- 真正的结果仍然以 `worker_report.json` / `report.json` 为准
- 对用户的“已完成 / 已推进”汇报只能以已 ingest 的 `report.json` / `status.json` 为准；`dispatch`、`spawn` 和执行窗口聊天文本都不算闭环证据

这份文档只定义当前仓库的最小 `dispatch + ingest harness v1`，目标是给“用户 -> 指挥官 -> 执行载体 -> 指挥官 -> 用户”链路补一层 repo-native transport，而不是重写指挥官体系，也不是引入通用多 agent 框架。

它当前也应明确视为外圈 transport 文档：

- 负责 `packet / report / ingest / status`
- 不负责定义指挥官身份、长期记忆和任务生命周期真相源
- 如果与 `指挥官任命.md`、`指挥官文档.md` 冲突，始终以前两者为准

## 1. 边界

本轮只解决 3 件事：

1. 指挥官把任务压成 machine-readable `task packet`
2. 执行窗口把结果压成 machine-readable `task report`
3. 指挥官通过 `dispatch / ingest / status` 回收结果，而不是继续靠长 prompt 串联

本轮明确不做：

1. 自动开窗
2. 多 worker 并行调度
3. 自动续派
4. 第二套长期记忆层
5. 改业务主链代码

一句话收口：文档仍是真相源，harness 只是 transport。

这里的“执行载体”当前默认可以是：

1. 子执行 agent
2. 外部执行窗口

差别在于载体不同，合同不变。

## 2. 合同文件

新增 2 个 schema：

1. `commander/transport/schemas/commander_task_packet.schema.json`
2. `commander/transport/schemas/commander_task_report.schema.json`

`task packet` 至少包含：

- `task_id`
- `title`
- `goal`
- `must_read`
- `bounds`
- `validation`
- `forbidden_paths`
- `report_contract`
- `status`

`task report` 至少包含：

- `task_id`
- `status`
- `summary`
- `changed_files`
- `verification`
- `commit`
- `risks`
- `recommended_next_step`
- `needs_commander_decision`

当前 schema 还允许一个可选 metadata：

- `harness_metadata.is_dispatch_draft`

另外还有 3 个可选控制字段：

- `needs_user_decision`
- `user_decision_reason`
- `ready_for_user_delivery`

worker 结果状态只收这 3 类：

- `done`
- `blocked`
- `need_split`

## 3. Runtime 落点

默认 runtime 根目录是 `.runtime/commander/`，当前仓库已经通过 `.gitignore` 忽略 `.runtime/`，因此 runtime 产物默认不会进入 git。

单个任务的最小落点如下：

```text
.runtime/commander/tasks/<task_id>/
  packet.json
  worker_brief.md
  worker_report.json
  report.json
  reports/
    <timestamp>.json
  events.jsonl
  status.json
```

含义：

- `packet.json`：指挥官发出的结构化任务
- `worker_brief.md`：给执行窗口直接消费的人读摘要
- `worker_report.json`：执行窗口直接填写的 report draft / 回执入口
- `report.json`：当前最新 worker report
- `reports/*.json`：历史回收快照
- `events.jsonl`：最小事件流
- `status.json`：当前 task / report / event 状态摘要

执行窗口本轮自行产出的 machine-readable 结果，推荐先放在任务目录旁边的：

- `.runtime/commander/tasks/<task_id>/worker_report.json`

dispatch 当前会预生成一份 schema-valid 的 `worker_report.json` draft，执行窗口在此基础上填写真实结果；draft 会显式带上 `harness_metadata.is_dispatch_draft: true`。

然后由指挥官执行 `commander_ingest.py --report ...worker_report.json`，再由 harness 归档为当前 `report.json` 和历史 `reports/*.json`。

ingest 除了 schema 校验，还会优先拒绝 `harness_metadata.is_dispatch_draft: true` 的 report；对旧 draft 仍保留占位语检查（例如 `待执行窗口填写`、`待填写`）作为短期兜底，避免把未真实填写的草稿收成正式回执。

这样分工的原因是：

- worker 只负责按合同产出结果
- ingest 才负责把结果收进 harness 当前态
- runtime 当前态和 worker 原始回执不会混在一起

## 4. 脚本职责

### 4.1 `commander/transport/scripts/commander_dispatch.py`

职责：

1. 接收指挥官输入
2. 产出 `packet.json`
3. 产出 `worker_brief.md`
4. 如不存在 `worker_report.json`，预生成一份 report draft
5. 写入 `task_dispatched` 事件
6. 刷新 `status.json`

最小示例：

```powershell
.\.venv\Scripts\python.exe scripts\commander_dispatch.py `
  --task-id harness-v1 `
  --title "落最小 harness v1" `
  --goal "补 dispatch ingest transport" `
  --must-read README.md `
  --must-read commander/outer/agent_workbench.md `
  --bound "只补 transport，不改业务主链" `
  --validation ".\\.venv\\Scripts\\python.exe -m pytest -q tests/test_commander_harness.py" `
  --forbidden-path config/rag.yml
```

### 4.2 `commander/transport/scripts/commander_ingest.py`

职责：

1. 读取 worker report JSON
2. 做 schema 校验，并优先检查显式 draft metadata
3. 写入当前 `report.json` 和归档副本
4. 写入 `task_report_ingested` 事件
5. 刷新 `status.json`

最小示例：

```powershell
.\.venv\Scripts\python.exe scripts\commander_ingest.py `
  --report .runtime\commander\incoming\worker-report.json
```

### 4.3 `commander/transport/scripts/commander_status.py`

职责：

1. 查看单任务当前状态
2. 或列出全部任务的最小状态摘要

最小示例：

```powershell
.\.venv\Scripts\python.exe scripts\commander_status.py --task-id harness-v1
.\.venv\Scripts\python.exe scripts\commander_status.py
```

## 5. 状态解释

`status.json` 重点看这些字段：

- `has_packet`
- `has_report`
- `packet_status`
- `worker_status`
- `needs_commander_decision`
- `commander_recommendation`
- `event_count`
- `last_event_type`

当前 `commander_recommendation` 只做最小推导：

- `awaiting_report`
- `needs_commander_decision`
- `ready_to_close`
- `missing_packet`

这层推导只服务 transport 观测，不替代指挥官决策。

### 5.1 控制面停机规则

当前控制面把“要不要停回聊天层”显式写进 `status.json / checkpoint.json`：

- `controller_handoff`
- `conversation_stop_required`
- `conversation_stop_reason`

默认规则已经收口成：

1. `continue`
   - 默认值
   - 表示应继续在指挥官控制环里推进，不要因为“刚完成一刀”就回到聊天等待用户确认
2. `wait_external_result`
   - 当前只用于 `awaiting_report`
   - 表示在等 worker / 外部结果，但不是用户决策点
3. `request_user_decision`
   - 只有当 report 显式写了 `needs_user_decision: true` 才允许进入
   - 这才是“必须停给用户拍板”的正式入口
4. `return_final_result`
   - 只有当 report 显式写了 `ready_for_user_delivery: true` 才允许进入
   - 表示当前结果已经可以由指挥官直接回给用户

这套规则的目标不是让 worker 自己决定一切，而是让“什么时候该继续、什么时候只是等结果、什么时候才真的停给用户”变成外部可见状态。

## 6. 设计原则落点

这版实现显式体现 5 条原则：

1. 用户只和指挥官交互
2. 执行窗口只做 worker
3. 阻塞、分叉、缺信息时先回指挥官
4. 文档是真相源，harness 是 transport，不是第二记忆层
5. 长链误差不能继续靠“把 prompt 写更长”解决

## 7. 当前没做什么

这版 v1 还没有：

1. 自动从 prompt 模板直接生成 packet
2. 自动打开执行窗口
3. 多 worker 编排
4. 自动写回 `commander/core/主文档.md` 或 `commander/state/时间线.md`
5. 更复杂的状态机和调度策略

因此它现在的定位很明确：先把 handoff 变成结构化合同，再谈更强自动化。

## 8. 模板如何和 harness 合同接通

当前推荐做法不是让指挥官继续把 `packet` 内容整段重写进长 prompt，而是：

1. 执行窗口任务模板只给出：
   - 项目路径
   - UTF-8 初始化
   - `worker_brief.md` 和 `packet.json` 路径
   - “以 packet 为合同”的硬规则
   - `worker_report.json` 输出路径和 report schema 路径
2. 执行窗口实际边界、必读文件、验证项、禁改路径都从 `packet.json` 读取
3. 执行窗口完成后，先按固定顺序做文字汇报，再落 `worker_report.json`
4. 指挥官再执行 ingest，把 worker 结果收回当前 `report.json`

一句话说：

模板现在负责“把执行窗口带到合同入口”，不再负责“重复抄写整份任务合同”。

补充一点：

- `worker_report.json` 现在可由 dispatch 预生成 draft，执行窗口不必再从零手写 JSON 骨架
- draft 只是填写起点，不应在未更新真实结果前直接 ingest
- 执行窗口填写真实结果时，应把 `harness_metadata.is_dispatch_draft` 改为 `false` 或删除该 metadata
- 对旧 report，如仍残留 `待执行窗口填写`、`待填写` 这类占位语，ingest 仍会报错并拒绝回收
