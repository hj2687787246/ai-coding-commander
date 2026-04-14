# 指挥官 LangGraph 运行时项目化方案

更新时间：2026-04-13

## 1. 项目定位

2026-04-14 定位修正：

这份文档是 Agent 仓库里的 LangGraph 运行时适配实验记录，不再定义通用“指挥官系统”的本体目标。

通用指挥官能力现在收束到 `commander-mode` skill：它负责帮助用户驾驭 AI coding agent、恢复状态、控制边界、回收证据和沉淀仓库记忆。LangGraph 只在某个仓库确实需要长期运行、可恢复、可观测的 agent runtime 时才作为可选适配器使用。

因此，本文中的“正式 AI 应用工程项目”“多 worker 指挥官控制面”等表述，只能理解为 Agent 仓库阶段性实验目标，不能外推成所有仓库都要安装或复制的通用框架。

这条主线的目标不是给现有脚本补一个 LangGraph adapter，也不是为了“最小化引入依赖”。

目标是把当前指挥官系统升级成一个正式的 AI 应用工程项目：

**一个由 LangGraph 驱动的、融合 Harness Engineering 与 Hermes Agent 思想的、可恢复、可观测、可治理的多 worker 指挥官控制面。**

项目价值取向：

1. 成熟 AI 应用框架优先，不重复手写低配 orchestration。
2. LangGraph 负责运行时编排、状态图、恢复、人类介入和多 worker 协作。
3. Harness Engineering 负责结构化交接、验证、观测、恢复和约束。
4. Hermes Agent 思想负责三层记忆、受控学习循环、skill 候选升级和工具权限治理。
5. 现有 `commander/` 文档体系继续作为项目真相源，LangGraph 不反客为主。
6. 外部上游模式优先吸收成熟接口，不复制整套宿主；其中 `deepagents` 的具体吸收边界与顺序见 [指挥官系统吸收DeepAgents落地清单.md](/D:/Develop/Python-Project/Agent/commander/outer/%E6%8C%87%E6%8C%A5%E5%AE%98%E7%B3%BB%E7%BB%9F%E5%90%B8%E6%94%B6DeepAgents%E8%90%BD%E5%9C%B0%E6%B8%85%E5%8D%95.md)

一句话定义：

**文档体系负责“事实和规则”，LangGraph 负责“把规则跑起来”。**

---

## 2. 为什么必须项目化引入

当前系统已经在手写很多 LangGraph 该承载的能力：

1. 状态机：`controller_handoff / conversation_stop_required / lifecycle`
2. 恢复：`checkpoint / resume_anchor / commander_resume.py`
3. 人类介入：`needs_user_decision / ready_for_user_delivery`
4. worker 编排：`worker_pool / ownership / tool_profile`
5. 观测：`audit / task_catalog / maintenance`
6. 学习循环：`improvement candidate / skill candidate`

继续沿着脚本堆叠，会逐步变成自研低配 LangGraph。

因此从本主线开始，默认原则改为：

**能由成熟 AI 应用框架承载的运行时编排能力，优先交给 LangGraph；repo-native 脚本保留为 adapter、兼容层和底层工具。**

---

## 3. 最终目标

最终指挥官运行时链路：

```text
用户目标
-> Commander Graph
-> 状态恢复 / 任务拆解 / ownership 分配
-> 多 worker 串行或并行执行
-> report ingest / audit / stop gate
-> 学习提案 / skill candidate / runtime archive
-> 指挥官对用户交付最终结果
```

最终系统必须具备：

1. 完整状态机
   - `intake`
   - `planning`
   - `dispatching`
   - `waiting_worker`
   - `ingesting`
   - `reconciling`
   - `asking_user`
   - `delivering_result`
   - `archiving`
   - `cleanup`
   - `learning_review`
2. 多 worker 协作
   - `code-worker`
   - `verifier-worker`
   - `docs-worker`
   - `maintenance-worker`
   - 并行必须受写集合 ownership 约束
   - worker provider 可替换，Codex 只是当前默认 provider，不是系统本体
   - 目标 provider 包括：
     - `codex`
     - `claude-code`
     - `qwen`
     - `doubao`
     - `local-script`
3. durable execution
   - 每条主线都有稳定 `thread_id`
   - 压缩、中断、worker 超时后能恢复到正确 node
   - 有副作用的 node 必须幂等或具备去重键
4. human-in-the-loop
   - 只有真实 `pending_user`、高风险取舍或最终交付才回用户
   - phase 完成、worker 等待、内部对账不再自动打断用户
5. 受控学习循环
   - `report -> candidate -> review -> approved/rejected -> applied -> archived`
   - skill 只能走候选与审批，不直接自动改 live skill
6. 观测与治理
   - 能回答当前卡在哪个 node
   - 能回答哪个 worker 持有哪些写集合
   - 能回答哪些 candidate 等审批
   - 能回答哪些 runtime task 可归档或清理
7. 作品集表达
   - 这不是“脚本合集”，而是一个可展示的 AI 应用控制面项目
   - 能讲清：为什么选 LangGraph、如何接 Harness、如何接 Hermes、如何防止长链误差累计
8. 执行模式合同
   - `clarify_mode`：先澄清边界与约束，不直接开工
   - `plan_mode`：先把目标压成 constitution / specification / planning / tasking
   - `team_mode`：同一 phase 内允许多个 worker 并行推进互不冲突 lane
   - `persistent_owner_mode`：由 daemon / 单一 owner 持续推进长任务直到真实 handoff
   - 这层语义进入 LangGraph state，而不是只停留在 prompt 习惯里
9. 上游模式吸收能力
   - 吸收 `deepagents` 的中间件组装、skills source precedence、compact/resume ledger、permission middleware 和 better-harness 实验场思路
   - 吸收结果必须落成 repo-native 合同、runtime 节点、候选审批链和验证，而不是只写成灵感

---

## 4. 目标目录结构

目标目录：

```text
commander/graph/
  README.md
  state.py
  graph.py
  nodes/
    restore.py
    plan.py
    dispatch.py
    wait.py
    ingest.py
    reconcile.py
    audit.py
    learn.py
    archive.py
    deliver.py
  adapters/
    commander_runtime.py
    worker_pool.py
    task_catalog.py
    filesystem.py
    worker_providers/
      base.py
      codex.py
      claude_code.py
      qwen.py
      doubao.py
      local_script.py
  policies/
    ownership.py
    stop_gate.py
    risk_gate.py
  runners/
    run_once.py
    resume.py
    inspect.py
  tests/
```

设计规则：

1. `graph.py` 只定义图和边，不塞业务细节。
2. `state.py` 定义 LangGraph 状态合同，与现有 `checkpoint/status/report` 做映射。
3. `nodes/` 负责可组合动作。
4. `adapters/` 调用现有 commander scripts / Python functions。
5. `adapters/worker_providers/` 只负责把统一 task packet 转给不同 worker provider，并把结果收敛为统一 worker report。
6. `policies/` 收敛 ownership、stop gate、risk gate。
7. `runners/` 提供本地运行、恢复和检查入口。
8. 现有 `commander/transport/scripts` 不立刻删除，先降级为 adapter 底座。

---

## 4.1 Worker Provider 抽象

最终系统不绑定 Codex。

Codex 当前只是最方便的开发宿主、指挥官宿主和 worker provider；未来应退到可插拔 provider 位置。

统一 provider 合同：

1. 输入统一 `task packet`
2. 遵守 `tool_profile / allowed_tools`
3. 遵守 `forbidden_paths`
4. 声明能力：
   - `read_files`
   - `edit_files`
   - `run_shell`
   - `run_tests`
   - `commit_git`
   - `review_only`
5. 输出统一 `worker_report`
6. 返回 `done / blocked / need_split`
7. 附带验证证据或阻塞原因

第一阶段 provider 分层：

1. `codex`
   - 当前默认执行 provider
   - 适合：代码改动、测试、提交、子 agent 协作
2. `claude-code`
   - 目标代码执行 provider
   - 适合：代码改动、重构、工程任务
3. `qwen`
   - 目标分析 / review / 文档 provider
   - 适合：方案审阅、中文文档、候选提案
4. `doubao`
   - 目标中文表达 / 文档辅助 provider
   - 适合：文档润色、说明归纳、非高风险分析
5. `local-script`
   - 确定性执行 provider
   - 适合：测试、lint、catalog、audit、cleanup

核心规则：

**换模型或换工具，只应该换 worker provider adapter，不应该重做指挥官系统。**

---

## 4.2 Execution Mode Contract

这里吸收 `oh-my-codex` 的不是 `.omx/` 目录结构，而是它对执行模式的拆分方式。

当前项目统一把这层落成 machine-readable runtime mode：

1. `clarify_mode`
   - 对应吸收：`deep-interview`
   - 用来先补需求、边界、风险，不直接派工
2. `plan_mode`
   - 对应吸收：`ralplan`
   - 用来先产出 `specification / planning / tasking`
3. `team_mode`
   - 对应吸收：`team`
   - 用来在同一 phase 内并行派发多个互不冲突 goal
4. `persistent_owner_mode`
   - 对应吸收：`ralph`
   - 用来让 daemon/单一 owner 持续推进长任务，不因单次聊天回合结束而停机

约束：

1. 不复制第二套 runtime 目录。
2. 不把每个 worker 变成完整 commander 副本。
3. mode 进入 graph state / runtime contract，而不是只写在提示词里。

---

## 5. 里程碑

### Milestone 0：依赖与架构决策

目标：

- 正式引入 LangGraph 的工程决策，而不是继续讨论是否应该用。

产物：

1. 依赖评估与引入方式
2. `commander/graph/README.md`
3. LangGraph state 合同草案
4. 现有 scripts -> graph adapter 映射表

完成判据：

1. 能解释 LangGraph 在本项目里负责什么、不负责什么。
2. 能列出第一批要包成 node 的现有脚本。
3. 能确定第一条真实 graph 路径。

当前状态：已落地。

落地结果：

1. 依赖：`requirements.txt` 保留 `langgraph==1.1.6`，新增 `langgraph-checkpoint-sqlite==3.0.3` 作为跨进程 checkpoint 依赖。
2. 目录：已建立 `commander/graph/`，包括 state、graph、nodes、adapters、worker provider 合同和 runners。
3. 第一条路径：`restore -> audit -> stop_gate -> decide_next -> deliver_result | continue_internal`。
4. adapter 映射：
   - `restore` 复用 `commander_harness.refresh_status` 与 resume anchor。
   - `audit` 复用 `commander_audit.build_audit_report`。
   - `stop_gate` 复用 `commander_stop_gate.build_stop_gate_report`。
   - `decide_next` 暂由 graph 内部根据 stop gate 结果路由。

副作用边界：

1. `refresh_status` 会写 `status.json / checkpoint.json / resume_anchor.json`，因此 restore/status 类节点不是严格只读。
2. `build_stop_gate_report` 与 `build_audit_report` 也可能触发 `refresh_status`。
3. `dispatch / ingest / archive / cleanup` 暂不进入第一条 graph 主路径，等 Milestone 2/3 抽出幂等键和单 writer 约束后再接。

### Milestone 1：单线程 Commander Graph

目标：

- 先把指挥官内部续跑控制做成图，而不是继续靠聊天纪律。

目标图：

```text
restore
-> audit
-> stop_gate
-> decide_next
-> deliver_result | continue_internal
```

完成判据：

1. 有 `thread_id`。
2. 能跑一次 `run_once`。
3. 能从中断后 `resume`。
4. active 主线不能静默停到用户层。

当前状态：进行中，第一版可运行。

已验证：

1. `tests/test_commander_graph.py` 覆盖 active 任务卡路由到 `continue_internal`、无活跃任务路由到 `deliver_result`、SQLite checkpoint 跨 graph 实例恢复、CLI `run_once`。
2. 真实仓库 smoke：
   - `python -m commander.graph.runners.inspect --thread-id commander-5-6-smoke-sqlite`
   - 结果为 `route=continue_internal / stop_allowed=false / stop_gate_outcome=must_continue`
3. 同一 `thread_id` 通过 `resume` 再跑，仍返回 `continue_internal`。
4. stop gate 与 graph 现在都会返回 `continuation_required / continuation_mode`，把“本轮滚动执行窗结束”和“总任务允许停机”显式区分开，不再把 Codex 客户端那组 4 条计划当成总路线图边界。

### Milestone 2：Worker Orchestration

目标：

- 接入 worker pool、dispatch、wait、ingest、ownership。
- 这一阶段不是“做完一刀就停”的串行补丁，而是一个完整 phase；阶段内 4 个目标必须连续收口后，才算 Milestone 2 真正完成。

目标图：

```text
plan
-> assign_owner
-> dispatch_worker
-> wait_worker
-> ingest_report
-> reconcile
```

完成判据：

1. 同一写集合只能有一个 owner。
2. 能并行派不重叠写集合的 worker。
3. worker 超时不会触发双写。
4. ingest 后自动回到 graph 决策节点。
5. `archive / user_handoff` 接入后，graph 可以区分“内部继续 / 等待外部结果 / 允许回用户层 / 可归档终态”。
6. 连续执行 driver 可以在 `continuation_required=true` 时自动续跑，而不是把一次 `invoke` 收敛当成总任务完成。
7. 至少一条真实 provider 回路已打通，形成真实 `packet -> worker -> report -> ingest` 闭环。
8. 有一条长任务 E2E 验收链，覆盖 active 不静默停机、wait_external_result 不误判完成、close/archive/user_handoff 正常收敛。
9. 阶段内剩余目标必须进入机器可读 `phase plan / goal queue`，而不是只写在人类任务卡里；只要 backlog 未清空，系统就不能因为当前 goal 收口而误停。
10. 指挥官对当前任务的“更新 / 追加 / 改写”必须受主题约束，只允许在同一 `phase_key/theme_key` 内进行。

阶段内 4 个目标：

1. `Goal 1`：补 `archive / user_handoff` 节点。
2. `Goal 2`：落连续执行 driver。
3. `Goal 3`：接首个真实 provider 派发回路。
4. `Goal 4`：补长任务 E2E 验收。

当前状态：进行中，`5.7 多 Worker 并行调度与会话复用` 这一段 phase 已完成收口；下一段重点转向真实 host/runtime adapter 与更强的宿主集成，而不是继续证明并行/复用闭环。

已落地：

1. 新增 `commander/graph/policies/ownership.py`，在 graph 层阻止同一 task 存在 active worker lease 时再次派 worker。
2. 新增 `commander/graph/adapters/worker_pool.py`，复用现有 warm worker slot / lease 机制。
3. 新增 `assign_worker -> dispatch_worker -> ingest_worker` 节点，其中 dispatch / ingest 已接到 graph-native import 函数，而不是再绕 CLI。
4. ingest 后已可自动进入 `close_task`，把 `ready_to_close` 收到 `closed`。
5. 已补测试覆盖：
   - 有 worker packet 时能拿到 worker lease。
   - 同 task 第二次派发会 blocked，不会产生第二个 active leased worker。
   - graph dispatch 会写入 packet / brief / worker draft，且重复执行同一 graph idempotency key 不会重复 append dispatch event。
   - graph ingest 会写入 report / archived report / improvement candidate，且重复执行同一 graph idempotency key 不会重复 append ingest/candidate event。
   - graph ingest 后若状态进入 `ready_to_close`，会自动 close 成 `closed`。
6. 已新增 `archive_task` 节点，把 `closed -> archived` 接进 graph；也已新增 `user_handoff` 节点，把 `ready_for_user_delivery / pending_user` 收敛成 graph-native 用户交付出口。
7. 已新增 `run_until_handoff` 连续执行 driver：
   - 遇到 `continuation_required=true` 会继续 resume
   - 遇到 runtime 已落盘的 `report.json` 会自动捡起并继续 ingest
   - 只有 `user_handoff / terminal / waiting_external_result / no_progress` 才会停
8. 已新增 objective-level supervisor：
   - `commander_objective_plan.py` 与 `commander_objective_plan.schema.json` 把“长期目标 -> 多个 phase”的顺序也变成机器可读 backlog
   - `run_until_objective_handoff` 不再把“某个 phase 做完后出现 terminal”误当成整条长期目标完成；只要 objective 里还有 pending phase，就继续 promote 下一段
   - `stop_gate` 现在同时读取 runtime task / phase plan / objective plan，因此真正允许停到用户层的只剩 `user_handoff / wait_external_result / objective terminal / no_progress`
9. 已接首个真实 provider：`local-script`
   - `dispatch_worker` 在 `worker_provider_id=local-script` 时会同步执行 provider
   - provider 会把命令结果收敛成统一 `worker_report`
   - graph 可在同一链路里继续 `ingest -> close -> archive`
10. 已补长任务 E2E 回归：
   - active 任务不会静默停机
   - wait_external_result 不会误判完成
   - ready_for_user_delivery 会进入 user_handoff
   - local-script inline provider 能完成端到端闭环
11. 已新增 `commander_phase_plan.py` 与 `commander_phase_plan.schema.json`
    - phase 内 goal 变成机器可读 backlog，而不再只留在人类任务卡文字里
    - 支持 `create / append-goal / rewrite-goal / promote-next-goal / status`
12. 已补主题约束与 phase 续跑规则
    - 追加和改写 goal 必须满足同一 `phase_key/theme_key`
    - stop gate 现在会读取 active phase summary；只要 `remaining_goal_count > 0`，就返回 `continuation_required=true`
13. 已把 `promote_phase_goal` 接进 graph 与 runner
    - `decide_next` 可在没有显式 packet 时，按 phase backlog 自动提升下一个 goal
    - `run_until_handoff` 会跟随 promoted `task_id` 继续等待 report / 自动 ingest，不再只盯住旧 task_id
14. 已把 `codex / claude-code / qwen / doubao` 接进统一的 `external_window` provider 合同
    - 外部窗口型 provider 不再是 `NotImplemented`
    - dispatch 现在会为它们生成统一 launch bundle，明确 `packet / worker_brief / worker_report / resume_anchor / checkpoint` 路径
    - `run_until_handoff` 继续沿 `waiting_worker -> report ingest` 主链工作
15. 已补 graph 级多任务验收
    - 两个不重叠 task 可同时通过 `codex` provider 派发
    - runtime 内可同时存在两个健康 busy worker lease，证明控制面级别已经接受多任务并行而不是只靠底层 worker pool 脚本证明
16. 已落地第一版自动上下文路由
    - `commander_context_router.py` 与 `commander_context_bundle.schema.json` 会在 dispatch 时生成 `context_bundle.json`
    - `context_router` 现已进入 budget-aware routing：entry 会显式带 `priority / budget_behavior / budget_action / budget_reason`，并在 router 预计 `open_now` 超过 `round_budget_tokens` 时，把低优先级 open paths 自动推入 `deferred_paths`
    - bundle 当前按 `task packet + provider_id + runtime artifacts` 选择最小上下文，不再只靠长 prompt 把整段背景灌给外部 worker
    - external-window provider 的 launch bundle 已显式加入 `context_bundle.json`，读序变成 `worker_brief -> packet -> context_bundle -> resume_anchor -> checkpoint`
17. 已落地 phase backlog 级并行派工第一刀
    - `commander_task_packet` 现已支持 `owned_paths`
    - `commander_phase_plan` 现已支持 `parallel_dispatch_limit / current_goal_ids / current_task_ids`
    - `commander_host_daemon.py` 会在 objective runner 前预填充不冲突的 ready goals，不再只盯住单个 `current_task_id`
    - 聚焦回归已通过 `tests/test_commander_phase_plan.py tests/test_commander_objective_plan.py tests/test_commander_host_daemon.py`
18. 已落地 worker session card 与 mailbox 基础层
    - `commander_host_runtime.py` 现已把 `worker_id / worker_profile / tool_profile / allowed_tools / forbidden_paths / owned_paths / reuse_allowed / context_revision` 纳入 host session
    - 每个 session 都会生成 `session_card`，并在 `.runtime/commander/host_runtime/mailboxes/*.jsonl` 写入 `session_created / session_updated`
    - `build_host_runtime_summary(...)` 与 `commander_host_control.py status` 会暴露 `session_cards / session_pool`
    - 聚焦回归已通过 `tests/test_commander_host_runtime.py tests/test_commander_host_control.py tests/test_commander_host_daemon.py`
19. 已落地 host session 复用候选查询
    - `commander_host_runtime.py reuse-candidates` 可按 provider / worker profile / tool profile / allowed tools / owned paths 查找释放后复用候选
    - 查询会显式返回 `candidate_count / can_accept_new_task_count / candidates / rejected_sessions`
    - 当前仍固定 `can_accept_new_task_count=0`，因为 active session 必须先完成 report ingest / release，不能被当成可直接接新任务的 detached worker
20. 已落地 host session release-to-reusable 状态转换
    - `commander_host_runtime.py release-reusable / release-task-reusable` 会把允许复用的 session 显式释放为 `released_reusable`
    - 只有该状态会让 `reuse_eligibility.decision=reusable_now` 且 `can_accept_new_task=true`
    - 当前仍不自动把新任务发进旧 session，下一步需要补新 task 绑定、delta context 和 mailbox command 消费
21. 已落地 reusable host session 重新绑定 task
    - `commander_host_runtime.py assign-reusable` 会把 `released_reusable` session 重新绑定到新 `task_id / thread_id`
    - 绑定时记录 `reuse_count / reused_from_task_id / task_history / dispatch_kind=reuse`
    - mailbox 会追加 `assign_task` 事件；绑定后 session 回到 `waiting_worker`，因此不再显示为可直接接下一单
22. 已接入 external-window dispatch 自动复用选择
    - `ExternalWindowHostRuntimeAdapter.create_or_attach_session(...)` 会在 `reuse_allowed=true` 时先查 released reusable 候选
    - 匹配 provider / worker profile / tool profile / allowed tools / owned paths 后走 `assign-reusable`
    - 无匹配候选时仍回退到 `create_host_session(...)`，不影响 fresh dispatch
23. 已落地 host session mailbox 命令读取入口
    - `commander_host_runtime.py mailbox --commands-only` 可以读取单 session mailbox 命令流
    - 命令事件已覆盖 `assign_task / inspect_session / resume_session / stop_session`
    - 支持 `after_sequence` 增量拉取
24. 已落地 host session mailbox ack
    - `commander_host_runtime.py ack-mailbox` 会记录 `mailbox_ack_sequence / mailbox_ack_at`
    - `mailbox --unacked-only --commands-only` 会按 ack sequence 过滤已消费命令
    - 当前覆盖“不重复消费 assign_task / inspect_session / resume_session / stop_session”
25. 已落地复用窗口 delta context 元数据
    - `assign-reusable` 的 session payload 会带 `context_delivery_mode=reuse_delta`
    - mailbox `assign_task` 事件会带 `context_delta_paths`
    - `context_paths_diff` 会显式列出 `added_paths / changed_paths / removed_paths / unchanged_path_keys`
26. 已落地 host session mailbox retry
    - `commander_host_runtime.py retry-mailbox` 会按 `mailbox_retry_sequence` 重新投递未 ack 命令
    - retry 事件保留 `retry_count / retry_of_sequence / command_id`，worker 可通过 `mailbox --unacked-only --commands-only` 只看到新 retry 命令
27. 已完成 graph 级多 worker E2E 收口
    - `tests/test_commander_graph.py::test_commander_graph_multi_worker_e2e_reuses_mailbox_and_closes` 现已覆盖 `2` 个并行 code task、`1` 个 local-script verifier lane、`inspect_session -> retry-mailbox -> ack-mailbox`、`release-reusable -> assign-reusable`、`context_paths_diff`、worker report ingest 与 session `close -> archive`
    - 组合验证已通过 `.\\.venv\\Scripts\\python.exe -m pytest -q tests\\test_commander_graph.py tests\\test_commander_host_runtime.py tests\\test_commander_host_control.py tests\\test_commander_host_daemon.py tests\\test_commander_worker_providers.py tests\\test_commander_objective_plan.py tests\\test_commander_phase_plan.py` 的 `58 passed`，以及对应 `ruff check`
    - 这说明 `5.7` 当前已经从“最后一轮待验收”进入“可归档稳定事实”，后续残留缺口转到真实自动拉起外部 provider 与更强 detached session pool / host integration

未接入：

1. `codex / claude-code / qwen / doubao` 的实际 host/runtime 自动集成；当前仍是“统一外部窗口 handoff 合同”，不是自动拉起外部执行器。
2. 更强的 detached session pool；当前 session card、mailbox 基础层、复用候选查询、release-to-reusable、`assign-reusable`、external-window 自动优先复用、mailbox 命令读取、ack 去重、retry、多命令类型和 context diff 已落地。
3. 更完整的等待 / 轮询 / 外部结果恢复编排，尤其是 objective supervisor 落地之后的 host wait / resume 集成与非阻塞长驻回收。
4. provider 发现机制仍是静态注册；当前动态的是上下文装配，不是 provider 插件动态 import。

当前活跃主线：`DeepAgents Phase B / Tool / Path Governance Middleware`

1. 当前目标：把 `allowed_tools / forbidden_paths / owned_paths` 从 packet/contract 字段升级成更统一的 runtime governance layer。
2. 已完成的前置条件：
   - `DeepAgents Phase A / Compact / Resume Ledger` 已完成第一轮正式落地
   - task/objective handoff 已拥有 `compaction_event.json + compactions/*.json`
   - `commander_resume.py` 默认优先读取 `compaction_event.json`
3. 当前切片：
   - 已落地统一的 `tool_policy / path_policy`
   - `owned_paths` 与 `forbidden_paths` 的明显重叠现在会在 dispatch 前被拒绝
   - 通过的 dispatch 也会把治理快照带进 `worker_dispatch` 与 host session `session_card.governance`
   - `external_window` 的 launch prompt 与 machine-readable `launch_bundle` 现在也会显式带出 `tool_profile / allowed_tools / forbidden_paths / owned_paths / governance`
   - `ingest_worker_report(...)` 现在会把 `changed_files` 与 packet 的 `forbidden_paths / owned_paths` 对齐，越界 report 会在回收侧被拒收
   - `context_bundle` 已升级为 `read_policy + summary_lines + deferred_paths` 的渐进式披露合同，执行窗口默认先读 metadata 和必读入口，再按需展开延迟路径
   - `status / checkpoint / resume_anchor` 现已补上 `context_budget` 启发式估算，能显示这轮 `open_now / deferred / full_expand` 的预计 token 与相对预算占比，用来解释“为什么这一轮会贵”
   - 下一刀继续把治理从 `preflight -> session_card -> launch bundle -> ingest guard -> context delivery` 往 provider 执行期更强的 post-check/filter 收紧
4. 进入原因：
   - `5.6 LangGraph 运行时项目化` 与 `5.7 多 Worker 并行调度与会话复用` 已完成收口
   - 当前连续性问题已经先通过 Phase A 收住，下一步最值钱的是把治理层做硬，避免能力增加后边界继续飘
5. 完成判据：
   - provider/tool/path 组合的 allow/deny 逻辑可机器解释
   - worker provider 不能绕过治理层直接执行越界动作
   - deny/allow/reject 有回归面，而不是只靠约定俗成

后续 phase backlog：`Host Runtime Integration`

1. `Goal 1`：把 `codex / claude-code / qwen / 豆包` 接到真实 host/runtime adapter，而不是只生成 launch bundle。
   - 当前进展：已落地第一版 `host session/runtime` 合同，新增 `commander_host_runtime.py` 与 `host_runtime` adapter；`external_window` provider dispatch 时会创建 `.runtime/commander/host_runtime/sessions/*.json`，统一托管 `thread_id / task_id / provider_id / host_controls / launch bundle paths`
   - 当前进展：`status / checkpoint / resume_anchor` 现在都会带出 `host_session` 摘要；`run_until_handoff` 在发现 `report.json` 时会先把 session 标成 `report_ready`，ingest 后会自动把关联 session 关到 `closed`
   - 当前进展：`external_window` provider 现已支持显式 opt-in 的 `provider_input.launcher`；fresh session 会先进入 `pending_launch`，自动拉起成功后切到 `waiting_worker`，失败时切到 `failed`，并把 `launch_status / launch_result` 投影到 `launch_bundle / session_card / host runtime summary`
   - 当前进展：provider-specific launcher preset 已收成独立 `launcher policy`：provider registry 只声明 `supported_launcher_presets`，具体 preset 定义与解析放在 `commander/graph/policies/launcher.py`，避免把 provider registry 变成宿主命令表
   - 当前进展：host session 现在已升级为可读状态卡，包含 `worker_id / worker_profile / tool_profile / owned_paths / reuse_eligibility / mailbox_path / next_action`，但 `can_accept_new_task` 仍明确为 false，等待 detached warm session pool 落地
   - 当前进展：`commander_host_runtime.py reuse-candidates` 已补只读复用候选查询，可提前筛出“释放后值得复用”的 session，同时保留 `can_accept_new_task=false` 的安全边界
   - 当前进展：`release-reusable / release-task-reusable` 已补 release-to-reusable 显式状态转换；释放后的 session 会进入 `released_reusable / reusable_now / can_accept_new_task=true`，但尚未自动接收新 task
   - 当前进展：`assign-reusable` 已补复用绑定入口；新 task 可绑定到 released session，mailbox 追加 `assign_task`，session 回到 `waiting_worker`
   - 当前进展：external-window host adapter 已接入自动优先复用 released session；有匹配候选时不会新建 session，无匹配候选时回退 fresh session
   - 当前进展：`commander_host_runtime.py mailbox --commands-only` 已能读取 `assign_task` 命令流，worker 可按 `after_sequence` 增量拉取 mailbox
   - 当前进展：`ack-mailbox` 已能记录消费到的 sequence，`mailbox --unacked-only --commands-only` 能避免重复返回已 ack 的 `assign_task`
   - 当前进展：`send-command / retry-mailbox` 已接入 host runtime，mailbox 命令类型覆盖 `assign_task / inspect_session / resume_session / stop_session`
   - 当前进展：`assign_task` 事件已携带 `context_delivery_mode=reuse_delta / context_delta_paths / context_paths_diff`，复用窗口可以按引用路径读取增量上下文入口并看到路径级 diff
2. `Goal 2`：补可见宿主层，让系统具备 `start / stop / status / inspect / resume` 这类明确宿主管理入口，而不是只有 runner 脚本和 `.runtime/commander` 文件。
   - 当前进展：已落地第一版 `commander_host_control.py`，把 `status / run-task / run-objective / inspect-session / resume-session / stop-session / heartbeat-session` 收成统一宿主控制入口
   - 当前进展：这一层已从可见 CLI control surface 推进到第一版常驻 daemon；新增 `commander_host_daemon.py`，状态、命令队列和 JSONL 日志统一落在 `.runtime/commander/host_daemon/`，并通过 `commander_host_control.py start-daemon / daemon-status / daemon-logs / stop-daemon / resume-daemon` 管理
3. `Goal 3`：补 `wait / poll / resume / timeout / ingest` 闭环，让 objective supervisor 能稳定等待外部 worker 并自动回收。
   - 当前进展：`run_until_handoff` 已改成 host-aware wait flow，按 `host session -> attached report -> worker_report.json -> report.json` 的顺序发现可回收结果，并忽略 dispatch 预生成的 draft `worker_report.json`
   - 当前进展：等待超时后会自动把 host session 标成 `resume_requested`，并把 `host_wait` 诊断统一暴露到 `status / checkpoint / resume_anchor / stop_gate / commander_host_control`
   - 当前进展：daemon loop 会在 `waiting_external_result / idle` 下保持后台存活并按配置继续执行 objective supervisor，不再依赖聊天窗口反复输入“继续”来触发下一轮
4. `Goal 4`：补多 worker 写集合分片、并行派发、phase backlog 并发提升的 graph 级验收，并把 intent binding 再往聊天入口上接。
   - 当前进展：`commander_host_control.py` 现在会返回 `waits / wait_summary`，可以直接观察多 task 并行等待的 provider 分布、超时等待数和 `resume_requested` 数
   - 当前进展：可见宿主入口已接通 `last_open_offer / pending_user_reply_target / offer_confirmed / latest_user_reply_text`，高层聊天入口调用 host control 时不会再丢掉 intent binding 所需输入
   - 当前进展：可见宿主层已新增批量 `resume-waits` 控制动作，可以按 provider 一次性恢复多路外部等待会话，把并行等待从“可观测”推进到“可批量调度”
   - 当前进展：`resume-daemon` 可携带 `last_open_offer / pending_user_reply_target / offer_confirmed / latest_user_reply_text` 写入 daemon 命令队列；聊天入口后续默认退为观察/干预层，而不是外层调度循环
   - 当前进展：phase backlog 现在已经具备 `parallel_dispatch_limit + owned_paths` 合同，daemon 也会在 objective round 前自动预填充可并行 goal；session card / mailbox 基础层、复用候选查询、release-to-reusable、assign-reusable、external-window 自动优先复用、mailbox 命令读取、ack 去重、retry、多命令类型、context diff 与 graph 级多 worker E2E 都已经落地，当前剩余缺口转到真实外部 provider 自动拉起与更强 detached session pool / host integration

这个 phase 按“一次授权、连续推进、阶段收口再回用户层”执行；单个 goal 完成只更新推进段和恢复锚点，不单独构成停机点。常驻 daemon 存在后，聊天窗口不再承担“外层继续按钮”职责；只有 daemon 进入 `waiting_user / attention_required`、真实阻塞或 phase 完整验收时，才需要回到用户层。

总体验收口径：

1. 这不是“从下列层里挑最重要的实现”，而是要把这些层全部落地到同一套项目里。
2. 最终系统必须同时具备：
   - `Constitution / Prompt Engineering`
   - `Specification / Spec-Driven Development`
   - `Context Routing / 上下文工程`
   - `Memory / 三层记忆`
   - `Orchestration / LangGraph 编排`
   - `Execution / Worker Provider`
   - `Host Runtime / 可见宿主层`
   - `Feedback / Report、Stop Gate、Learning Loop`
3. 里程碑和 phase 只表示交付顺序，不表示功能取舍；任何一层都不是“可选增强项”。

六张图工程映射：

1. 图 1：规则文件 + 上下文路由
   - 工程归属：`Constitution / Prompt Engineering + Context Routing`
   - 当前落点：
     - `commander/core/任命.md` 继续充当规则入口
     - dispatch 生成 `context_bundle.json`
     - external-window provider 显式读取 `worker_brief -> packet -> context_bundle -> resume_anchor -> checkpoint`
     - `context_bundle.json` 现已显式带 `read_policy / recommended_sequence`，并把每个 entry 收成 `summary_lines / paths / deferred_paths / when_to_open`
     - `worker_brief.md` 与 launch prompt 已切到 metadata-first 的渐进式披露，不再默认要求执行窗口把整批路由文档一次性全读完
   - 当前缺口：
     - 当前仍是 packet/bundle 驱动，不是 host daemon 按 session 热度自动预取或裁剪上下文
     - provider 发现机制仍是静态注册；当前动态的是上下文装配，不是 provider 插件动态 import。
2. 图 2：大任务拆小任务、按规划分步执行
   - 工程归属：`Specification / Planning / Tasking + Orchestration`
   - 当前落点：
     - `objective plan / phase plan / goal queue`
     - 主题约束、goal 自动提升、objective 级连续执行 supervisor
   - 当前缺口：
     - `Specification / SDD` 还没形成独立 artifact 层
     - 当前仍以任务卡 + runtime backlog 为主，不是 spec-first 交付
3. 图 3：ReAct 风险与反馈防空转
   - 工程归属：`Feedback / Stop Gate / Loop Guard`
   - 当前落点：
     - `stop_gate / continuation_required / continuation_mode / no_progress`
     - intent binding
     - report ingest 后回到 graph 决策链
   - 当前缺口：
     - 还缺更强的失败预算、重复错误分类、host wait/polling 下的反馈闭环
4. 图 4：AI Agent = 大模型 + Harness Engineering 各层
   - 工程归属：`Prompt + Context + Memory + Orchestration + Execution + Host Runtime + Feedback`
   - 当前落点：
     - 文档层已明确这些层全部必须实现
     - graph、memory docs、worker provider、report/stop gate 已分别落地
   - 当前缺口：
     - `Host Runtime / 可见宿主层` 已有第一版常驻 daemon，但真实自动拉起外部 provider 与 UI 仍未收口
5. 图 5：Spec-Kit / Spec-Driven Development
   - 工程归属：`Specification / SDD`
   - 当前落点：
     - `commander/specs/` 已落地为 repo-native spec artifact 层
     - `commander/transport/schemas/commander_spec_artifact.schema.json` 和 `commander/transport/scripts/commander_spec_kit.py` 已提供机器可读合同
     - `objective plan / phase plan / goal queue` 可以通过 `spec_refs` 挂载 spec artifact
     - `dispatch`、`worker_brief.md`、`context_bundle.json` 会显式带出 spec refs
    - 当前缺口：
     - 还需要继续把 spec_refs 的可见性补到 summary/status 输出里
     - 还需要继续围绕真实 phase / objective 任务补更多 spec artifact 示例
6. 图 6：Harness 把模型放进受控工程结构
   - 工程归属：`Worker Provider + Host Runtime + Governance`
   - 当前落点：
     - `codex / claude-code / qwen / 豆包 / local-script` 已进入统一 provider 合同
     - `tool_profile / allowed_tools / forbidden_paths / worker_report` 已形成治理边界
     - 外部窗口型 provider dispatch 时会创建托管 `host session`，并把 session 摘要写入 `status / checkpoint / resume_anchor`
     - `commander_host_control.py` 已提供第一版可见宿主控制入口
     - `commander_host_daemon.py` 已提供第一版常驻宿主循环，聊天窗口后续默认作为观察/干预入口
   - 当前缺口：
     - provider 仍是静态注册 + external-window handoff
     - 真实自动拉起与更强的 `wait/poll/resume` 仍在当前 phase

阶段执行规则：

1. `Goal 1 -> Goal 2 -> Goal 3 -> Goal 4` 是 Milestone 2 内部顺序，不是 4 个独立 milestone。
2. 单个 goal 完成后默认直接推进下一个 goal，只更新任务卡里的“当前推进段 / 恢复锚点”，不把它当默认停机点。
3. 只有当 4 个 goal 全部通过，或出现真实阻塞、依赖缺失、必须用户拍板的分叉，或 daemon 明确进入 `waiting_user / attention_required` 时，才允许把控制权交回用户层。
4. 如果长期目标被拆成多个 phase，则 phase 之间也不能靠聊天里的“继续”维持连续执行；必须进入 objective queue，由 runtime 自己决定是否 promote 下一段。

### Milestone 3：Durable Resume 与幂等副作用

目标：

- 把中断恢复从脚本级锚点升级成 graph 级恢复。

完成判据：

1. dispatch / ingest / archive / cleanup node 有幂等键。
2. 恢复不会重复执行危险副作用。
3. 压缩后能通过 `thread_id` 恢复到正确 node。
4. 用户短确认词（如 `可以 / 继续 / 好`）必须优先绑定到最近一次 assistant 明确提出的待执行提议，而不是回退绑定到更早的大主题。

补充缺口：

1. 当前系统已经能跟踪 milestone、phase、continuation 和 stop gate；第一版 intent binding 显式状态现已落地，用来表达：
   - `last_open_offer`
   - `pending_user_reply_target`
   - `offer_confirmed`
2. 当前已把这组状态接进 `run_once / resume_once / run_until_handoff`，并写回 `status.json / checkpoint.json / resume_anchor.json`，保证压缩上下文或恢复后仍能找回最近待确认提议。
3. 这类问题不是事实幻觉，而是对话承接漂移；应作为 `Durable Resume / conversational intent binding` 的一部分治理，而不是继续依赖聊天语感。
4. 当前仍未完成的是把这组绑定能力继续上接到更高层聊天入口，让用户短确认词从“runtime 可恢复”进一步升级到“端到端默认正确绑定”。

### Milestone 4：Learning Loop

目标：

- 把 Hermes 的受控进化回路接入 graph。

目标图：

```text
ingest_report
-> propose_improvement
-> review_candidate
-> apply_doc_or_script_or_skill_candidate
-> archive_candidate
```

完成判据：

1. 真实任务完成后自动生成 improvement candidate。
2. candidate 进入 review，不自动改 live skill。
3. approved 后可应用并归档。

### Milestone 5：Maintenance / Observability

目标：

- 把 `audit / archive / cleanup / catalog` 变成 graph 后处理与巡检能力。

完成判据：

1. graph run 可输出当前 node、worker、candidate、runtime 卫生状态。
2. maintenance node 能调用现有 `commander_maintenance` 能力。
3. inspect runner 能给出作品级可展示状态摘要。

### Milestone 6：作品级真实任务验收

目标：

- 证明这不是框架接入 demo，而是能承载真实工作的 AI 应用控制面。

完成判据：

1. 至少 2 个真实任务走完整 graph。
2. 至少 1 个任务发生中断/恢复。
3. 至少 1 个任务触发 worker ownership 检查。
4. 至少 1 个任务触发 learning candidate。
5. 最终形成可对外讲述的项目说明：
   - 痛点
   - 架构
   - 技术取舍
   - 可靠性机制
   - 结果证据

---

## 6. 非目标

本主线不追求：

1. 推翻现有 `commander/` 文档真相源。
2. 把所有 commander scripts 一次性删掉。
3. 无审批自动改 live skill。
4. 把所有聊天历史塞进长期记忆。
5. 上来就接 LangGraph 部署平台或外部观测平台。

这些可以作为后续增强，但不作为本主线第一阶段阻塞项。

---

## 7. 执行纪律

1. 本主线不以“最小化”为默认价值。
2. 但每个 milestone 必须有边界和验收标准。
3. 每个有副作用的 graph node 必须说明幂等策略。
4. 每个 worker node 必须说明 ownership 写集合。
5. 每次阶段完成后先跑 stop gate，再决定是否继续、等待、回用户或归档。
6. 如果引入依赖，需要同时更新依赖文件、验证命令和工程说明。
7. assistant 一旦向用户明确提出“下一步我可以做 X”，就应把这个 X 视作待执行提议；用户若用短确认词回应，默认优先绑定该提议，不能回跳到更早主题。

一句话规则：

**我们追求的是成熟 AI 应用工程，不是手写 orchestration 证明题。**
