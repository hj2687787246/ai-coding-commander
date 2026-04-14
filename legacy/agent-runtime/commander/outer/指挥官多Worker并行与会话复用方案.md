# 指挥官多Worker并行与会话复用方案

更新时间：2026-04-13

## 1. 任务定位

这条主线不是重新造一个 `oh-my-codex`，也不是把当前指挥官系统重新推倒。
目标是承接现有 `commander/graph + host_runtime + worker_provider`，把当前“能派工、能等待、能回收”的控制面，升级成“可并行、可复用、可持续调度”的运行时。

一句话定义：

**让指挥官从“单 worker 阻塞式回合调度”升级成“多 worker 并行 + 会话复用 + 状态可观测”的 LangGraph runtime。**

## 2. 现状判断

当前仓库已经具备这些基础：

1. graph 级 ownership，能阻止同一写集合被双写
2. host session 托管，能为外部 worker 建立 `session_id / status / heartbeat / resume / close`
3. `context_bundle.json`，能把最小上下文路由给 worker，而不是每次全量灌 prompt
4. `resume-waits` 与 wait summary，能观察多路等待中的 task/session
5. graph 级多任务验收，已经证明“不同 task 可以同时存在健康 busy lease”

当前真正的缺口不是“完全没有并行能力”，而是：

1. 外部 provider 仍以 `launch bundle` 为主，真实自动拉起与长驻复用能力不足
2. 调度主循环仍偏“当前 task 驱动”，而不是“ready queue 驱动”
3. worker 缺少统一的 machine-readable 状态卡，主控只能看到 session 摘要，看不到 lane 级工作状态
4. 聊天窗口仍在承担一部分“外层继续按钮”职责，daemon 还没完全接管

## 3. 吸收原则

这条主线会吸收 `oh-my-codex` 的思路，但不照搬它的运行形态。

吸收的部分：

1. durable worker runtime
2. worker mailbox / inbox / heartbeat / status card
3. 长任务不靠聊天记忆，靠 machine-readable state
4. leader 不因为单个 worker 等待而整体阻塞
5. execution mode 语义
   - `deep-interview -> clarify_mode`
   - `ralplan -> plan_mode`
   - `team -> team_mode`
   - `ralph -> persistent_owner_mode`

不吸收的部分：

1. 不把 tmux/team 作为本仓库默认运行时
2. 不把整个 commander prompt 原样共享给每个 worker
3. 不在 Windows + Codex App 环境里强行复制 CLI-first 工作流

默认技术路径：

**LangGraph 负责状态机与调度，host runtime 负责 session 托管，worker provider 负责异构执行器接入。**

## 4. 完成判据

这条主线完成时，系统至少要满足：

1. 指挥官能同时派发多个写集合不重叠的 worker
2. 任一 worker 进入等待，不会阻塞其他 ready task 继续被派发
3. 同 provider / 同 profile / 同上下文兼容的任务，优先复用已有 worker session
4. 每个 worker 都有 machine-readable 状态卡，主控可直接看到其状态、写集合、阻塞点和最近心跳
5. 聊天窗口退化为观察/干预面；持续调度由 daemon loop 完成
6. 多 worker E2E 链路可通过验证，且不会因重复 resume 或超时而造成双写

## 5. 执行路线

### Action 1：建立 Worker Session Contract 与状态卡

目标：

- 把当前 `host_session` 从“外部窗口摘要”升级成“可复用 worker session 合同”

要落地的内容：

1. 定义 `worker_session_card` schema
2. 补齐这些字段：
   - `session_id`
   - `provider_id`
   - `worker_profile`
   - `task_ids`
   - `write_sets`
   - `state`
   - `heartbeat_at`
   - `last_report_path`
   - `mailbox_path`
   - `context_revision`
   - `reuse_eligibility`
   - `blocker`
   - `next_action`
3. 明确 session 生命周期：
   - `warm_idle`
   - `assigned`
   - `running`
   - `waiting_input`
   - `waiting_report`
   - `blocked`
   - `closing`
   - `closed`

完成判据：

1. 任一 worker session 都能独立读出当前状态卡
2. 主控无需读取聊天记录，就能判断该 session 是否可复用、是否卡住、是否应回收

当前进展：

1. `commander_host_runtime.py` 已经把 `worker_id / worker_profile / preferred_worker_profile / tool_profile / allowed_tools / forbidden_paths / owned_paths / reuse_allowed / dispatch_kind / closure_policy / context_revision` 落进 `host_runtime/sessions/*.json`
2. 每个 session 都会内嵌 `session_card` 摘要，并显式给出 `mailbox_path / blocker / next_action / last_report_path / reuse_eligibility`
3. `.runtime/commander/host_runtime/mailboxes/*.jsonl` 已经开始记录 `session_created / session_updated` 事件，host runtime 不再只是静态 JSON 快照
4. 当前 `reuse_eligibility` 仍是受控诊断层：会明确区分 `eligible_after_release` 与 `can_accept_new_task=false`，先把“是否值得复用”做成 machine-readable，再进入真正的 session pool
5. `commander_host_runtime.py reuse-candidates` 已能按 provider / worker profile / tool profile / allowed tools / owned paths 查询释放后复用候选，并输出拒绝原因与写集合 overlap；这一步仍是只读候选查询，不会绕过当前 task 释放与 report ingest

### Action 2：建立 Ready Queue 与并行调度器

目标：

- 把调度入口从“单 task 驱动”升级成“ready queue 驱动”

要落地的内容：

1. 从 objective / phase backlog 里筛出可并行的 ready tasks
2. 引入 `concurrency_budget`
3. 基于 `write_set / provider / tool_profile / risk_gate` 做并行可行性判断
4. 支持一次 dispatch 多个互不冲突的 task

完成判据：

1. 同一轮调度可以同时派出 2 个以上互不冲突 task
2. 任一 task 被阻塞，不会拖住其他 ready task 的派发

当前进展：

1. `commander_task_packet` 已补 `owned_paths`，作为并行写集合合同
2. `commander_phase_plan` 已补 `parallel_dispatch_limit / current_goal_ids / current_task_ids`
3. `commander_host_daemon.py` 现在会在 objective runner 前预填充不冲突的 ready goals
4. 这意味着 phase backlog 已经从“单 current_task 串行推进”升级成“有限并行槽位 + 非冲突 goal 自动补位”的第一版调度器
5. 当前未完成部分集中在 session 复用、mailbox、lane 级状态卡，而不是 phase 级并行合同本身

### Action 3：让 Daemon 接管 wait / resume / ingest / reconcile

目标：

- 把“继续按钮”从聊天窗口迁到 daemon

要落地的内容：

1. daemon 循环持续做：
   - dispatch ready tasks
   - monitor active sessions
   - ingest ready reports
   - reconcile ownership/session state
   - promote next ready work
2. `wait_external_result` 不再等价于聊天层停机
3. timeout / stale / missing heartbeat 进入自动恢复或回收路径

完成判据：

1. 某个 worker 长时间等待时，daemon 仍能继续调度其他 lane
2. 聊天窗口退出后，runtime 仍可继续推进到真正 handoff

当前进展：

1. daemon 已经不再只围着单个 `current_task_id` 转；只要 active phase 还有可用并行槽位，就会先 dispatch 其他 ready lane
2. host runtime 摘要现在已带 `session_cards / session_pool`，daemon 与 host control 不必再靠聊天窗口猜测 worker lane 状态
3. 当前 daemon 仍然更偏“phase backlog 驱动”，真正的 detached session pool / mailbox 命令消费 / lane card 复用决策还在后半段
4. 因此这一步现在可以按“非阻塞调度主循环已起步，session card 与 mailbox 基础已落地，会话复用器还在后半段”理解

### Action 4：建立 Session 复用与增量上下文装配

目标：

- 降低重复建 worker 带来的上下文和通信成本

要落地的内容：

1. 定义“复用已有 session”的判定规则：
   - provider 相同
   - worker profile 相同
   - tool profile 相容
   - write set 不冲突
   - session 未脏化
2. 让复用优先发送增量上下文，而不是重发全量 bundle
3. 为 session 维护 `context_revision / bundle_digest`

完成判据：

1. 可复用场景下不再重新建 session
2. 复用时只下发 delta 或引用已有 bundle
3. 调度日志可明确说明“为何复用 / 为何新建 / 为何回收”

当前进展：

1. 已落地只读候选查询：`commander_host_runtime.py reuse-candidates`
2. 查询会返回 `candidate_count / can_accept_new_task_count / candidates / rejected_sessions`
3. 已落地显式释放入口：`commander_host_runtime.py release-reusable / release-task-reusable`
4. 只有 `released_reusable` 状态会把 `reuse_eligibility.decision` 提升为 `reusable_now`，并让 `can_accept_new_task=true`
5. 已落地复用绑定入口：`commander_host_runtime.py assign-reusable`
6. `assign-reusable` 会把 released session 重新绑定到新 task，记录 `reuse_count / reused_from_task_id / task_history / dispatch_kind=reuse`，并向 mailbox 追加 `assign_task` 事件
7. `ExternalWindowHostRuntimeAdapter.create_or_attach_session(...)` 已经在 `reuse_allowed=true` 时优先查询并复用 `released_reusable` session，匹配失败才创建新 session
8. `commander_host_runtime.py mailbox --commands-only` 已经能读取 mailbox 命令流，命令类型覆盖 `assign_task / inspect_session / resume_session / stop_session`，并支持 `after_sequence` 增量拉取
9. `commander_host_runtime.py ack-mailbox` 已经能记录 `mailbox_ack_sequence / mailbox_ack_at`，并配合 `mailbox --unacked-only --commands-only` 避免重复消费同一条命令
10. `commander_host_runtime.py send-command / retry-mailbox` 已经能投递 inspect/resume/stop 命令并重投未 ack 命令，retry 会记录 `mailbox_retry_sequence / retry_count / retry_of_sequence`
11. `assign-reusable` 的 session 与 mailbox `assign_task` 事件已经携带 `context_delivery_mode=reuse_delta`、`context_delta_paths` 和 `context_paths_diff`
12. 绑定后 session 会回到 `waiting_worker`，因此 `can_accept_new_task` 会重新降为 false；下一步进入多 worker E2E 收口验收

### Action 5：补 Mailbox 与多Worker E2E 验收

目标：

- 让系统真正具备“多 worker 并行协作且可回收”的可验证证据

要落地的内容：

1. 为 worker session 加 mailbox / inbox
2. 主控可对单 session 或 provider 批量发 resume / nudge / inspect
3. 设计并通过多 worker E2E：
   - 2 个并行 code task
   - 1 个等待中的外部 worker
   - 1 个 local-script verifier lane
   - 中途 timeout / resume / ingest / close / archive

完成判据：

1. 多 worker 并行链路稳定通过
2. 不出现重复 ingest、重复 dispatch、双写或失管 session
3. stop gate 能正确区分：
   - 还有并行 work 在跑
   - 只是某一路在等
   - 真正可以回用户层

当前进展：

1. `tests/test_commander_graph.py::test_commander_graph_multi_worker_e2e_reuses_mailbox_and_closes` 已新增 graph 级多 worker E2E 验收，覆盖 `2` 个并行 code task、`1` 个 local-script verifier lane、`inspect_session -> retry-mailbox -> ack-mailbox`、`release-reusable -> assign-reusable`、`context_paths_diff`、worker report ingest 与 session `close -> archive`
2. 当前这条 E2E 说明 `send-command / retry-mailbox / mailbox --unacked-only --commands-only / context_paths_diff` 已经和 graph 回收链路连上，不再只是 host runtime 单点命令
3. 组合验证已通过 `.\\.venv\\Scripts\\python.exe -m pytest -q tests\\test_commander_graph.py tests\\test_commander_host_runtime.py tests\\test_commander_host_control.py tests\\test_commander_host_daemon.py tests\\test_commander_worker_providers.py tests\\test_commander_objective_plan.py tests\\test_commander_phase_plan.py` 的 `58 passed`，以及对应 `ruff check`
4. `Action 5` 当前可按“已收口”理解；后续若继续推进，这条主线的下一阶段不再是证明并行/复用是否能闭环，而是决定是否把 `external_window` provider 从 handoff 合同推进到真实自动拉起宿主

当前阶段结论：

- `Action 1 -> Action 5` 已全部形成稳定基线，因此 `5.7 多 Worker 并行调度与会话复用工程` 已从当前任务卡归档
- 当前保留下来的真实边界是：`external_window` provider 仍然依赖手动窗口接力，host runtime 负责托管、复用和回收，但不负责自动拉起外部执行器

## 6. 非目标

当前不做：

1. 直接把 `oh-my-codex team/tmux` 整体搬进仓库
2. 直接把每个 worker 变成完整 commander 副本
3. 在 Windows + Codex App 上强做不安全的自动开窗注入
4. 为了追求并行而放宽写集合 ownership 约束

## 7. 执行顺序

默认顺序固定为：

1. `Action 1` 先做合同与状态卡
2. `Action 2` 再做 ready queue 与并行调度
3. `Action 3` 再把 daemon 变成真正非阻塞主循环
4. `Action 4` 再补 session 复用与增量上下文
5. `Action 5` 最后做 mailbox 与多 worker E2E 验收

一句话规则：

**先把“谁在工作、能不能复用、谁该继续跑”变成 machine-readable，再把并行真正放大。**
