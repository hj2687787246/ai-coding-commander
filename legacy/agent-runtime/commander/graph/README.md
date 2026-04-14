# Commander Graph

`commander/graph` 是指挥官系统的 LangGraph 运行时层。

它的职责是把现有规则跑起来，而不是替代 `commander/core` 和 `commander/state`：

- `commander/core` 与 `commander/state` 继续保存事实、规则、任务卡和时间线。
- `commander/transport/scripts` 继续作为已验证的底层 harness 工具。
- `commander/graph` 负责状态机、恢复、路由、worker 编排与后续学习循环。

## Milestone 0 决策

本仓库已经在 `requirements.txt` 中固定 `langgraph==1.1.6`；本阶段新增 `langgraph-checkpoint-sqlite==3.0.3`，用于跨进程 checkpoint。

第一版 graph 采用 `StateGraph` + SQLite checkpointer 建立运行时骨架：

```text
restore -> audit -> stop_gate -> decide_next -> deliver_result | continue_internal
```

默认 checkpoint 文件：

```text
.runtime/commander/graph/checkpoints.sqlite
```

`InMemorySaver` 只作为单元测试或依赖未安装环境的 fallback。Milestone 3 继续补充 dispatch / ingest / archive / cleanup 等有副作用 node 的幂等键与重复执行保护。

参考：

- LangGraph overview: <https://docs.langchain.com/oss/python/langgraph>
- LangGraph durable execution: <https://docs.langchain.com/oss/python/langgraph/durable-execution>

## Adapter 映射

第一版节点优先复用现有函数：

- `restore` -> `commander_resume.build_resume_anchor` + `commander_harness.refresh_status`
- `audit` -> `commander_audit.build_audit_report`
- `stop_gate` -> `commander_stop_gate.build_stop_gate_report`
- `decide_next` -> graph 内部路由

这些 adapter 的原则是：Graph 不直接读写散落文件，优先调用已有 transport 层函数。

注意：这些函数不是全部纯读。

- `refresh_status` 会刷新 `status.json / checkpoint.json / resume_anchor.json`。
- `build_stop_gate_report` 可能对目标 task 或已发现 task 调用 `refresh_status`。
- `build_audit_report` 会调用 `refresh_status`，也会以 dry-run 模式检查 worker slot。
- `dispatch / ingest` 暂不接入第一条单线程 graph；它们会写 packet、report、event、catalog 和 improvement candidate，必须等 Milestone 2/3 补齐幂等键与单 writer 约束后再接。

## Runner

第一版 CLI：

- `python -m commander.graph.runners.run_once --thread-id <id>`
- `python -m commander.graph.runners.inspect --thread-id <id>`
- `python -m commander.graph.runners.resume --thread-id <id>`

`resume` 会先读取同一 `thread_id` 的 checkpoint，并在输出的 `resume.had_checkpoint` 中显式标注是否读到旧状态。

## Continuation Contract

当前 graph 还是单次 invoke 的运行时，不是“自动永动机”。

也就是说，一次 `run_once` 或 `resume` 结束，只代表当前这一轮 graph 路由收敛了，不代表总任务已经完成。

为了避免把 Codex 客户端里那组 4 条左右的计划窗误当成总任务边界，stop gate 和 graph 现在都会返回：

- `stop_allowed`
- `continuation_required`
- `continuation_mode`
- `next_actions`

解释规则：

- `stop_allowed=true`：这轮允许回到用户层。
- `continuation_required=true`：这轮只是滚动执行窗结束，控制面仍要求继续推进。
- `continuation_mode=commander_internal`：需要继续内部拆下一刀或继续 dispatch。
- `continuation_mode=wait_external_result`：当前是 worker 结果未回收，不允许把等待误当完成。
- `continuation_mode=user_handoff` 或 `terminal`：才允许把这一轮收束到用户层。

一句话记忆：

**计划栏是滚动窗，不是总路线图；只有 `stop_allowed=true` 才是允许停机的机器信号。**

## Worker Orchestration

Milestone 2 的第一刀已经接入 graph 内部 ownership：

```text
decide_next -> assign_worker -> dispatch_worker
```

当前边界：

- `assign_worker` 会通过 `worker_pool` adapter 获取 worker lease。
- 如果同一个 task 已经有 active leased worker，graph 返回 `worker_orchestration.status=blocked`，不会再创建第二个 worker。
- `dispatch_worker` 现在会调用 `dispatch_task(...)`，把 packet / worker_brief / draft report / status 刷进 runtime，并用 graph `idempotency_key` 避免重复 append dispatch event。
- `dispatch_task(...)` 现在还会生成 `context_bundle.json`：把任命文档、当前任务卡、LangGraph 方案、runbook、execution workbench 等上下文按 task/provider 动态路由成最小 bundle，而不是继续靠长 prompt 全量灌入。
- 当 `worker_provider_id=local-script` 时，`dispatch_worker` 会同步执行 provider，并把统一 `worker_report` 直接喂给后续 ingest。
- 当 `worker_provider_id=codex / claude-code / qwen / doubao` 时，`dispatch_worker` 会走统一 `external_window` provider 合同，生成 launch bundle，并沿 `waiting_worker -> report ingest` 主链等待外部窗口回写结果。
- 外部窗口型 provider 的 launch bundle 现在默认要求先读 `worker_brief.md -> packet.json -> context_bundle.json -> resume_anchor.json -> checkpoint.json`，避免只靠人工脑补“这轮到底该读哪些文档”。
- 外部窗口型 provider dispatch 现在会同步创建 `.runtime/commander/host_runtime/sessions/*.json`，把 `thread_id / task_id / provider_id / host_controls / launch bundle paths` 纳入统一 host session 托管。
- `status.json / checkpoint.json / resume_anchor.json` 现在都会带出 `host_session` 与 `host_wait` 摘要；`commander_status.py` 也会额外返回 `host_runtime` 汇总。
- `commander_host_control.py` 已提供第一版可见宿主控制入口：可以统一查看 `status`，以及运行 `run-task / run-objective / inspect-session / resume-session / stop-session / heartbeat-session`。
- `commander_host_control.py status` 现在会额外聚合 `waits / wait_summary`，可以直接观察多 task 并行等待的 provider 分布、超时等待数和 `resume_requested` 数。
- `commander_host_control.py run-task / run-objective` 现在会把 `last_open_offer / pending_user_reply_target / offer_confirmed / latest_user_reply_text` 透传给 runtime，避免高层入口丢失 intent binding 所需状态。
- `commander_host_control.py resume-waits` 与底层 `commander_host_runtime.py resume-waits` 现在都支持按 provider 批量把多路等待会话标成 `resume_requested`，让宿主层可以一次性接管并行等待。
- `commander_host_daemon.py` 已提供第一版常驻宿主循环：状态、命令队列和 JSONL 日志统一落在 `.runtime/commander/host_daemon/`，daemon 会持续消费 objective/phase/goal backlog，不再把聊天回合当成外层调度器。
- `commander_host_control.py start-daemon / daemon-status / daemon-logs / stop-daemon / resume-daemon` 已接到这层常驻宿主；聊天窗口默认只做观察和干预，真正的持续推进由 daemon loop 承担。
- phase plan / objective plan 现已支持 `parallel_dispatch_limit`；task packet / goal packet_template 现已支持 `owned_paths`，作为 phase backlog 级并行派工的写集合合同。
- `commander_host_daemon.py` 现在会在 objective runner 前先检查 active phase 的可用并行槽位，并通过 `promote_ready_phase_goals(...)` 预填充不冲突的 goal，再把控制权交回 LangGraph runner。
- `status`/`phase summary` 现在会显式暴露 `current_goal_ids / current_task_ids / active_goal_count / available_parallel_slots`，指挥官可以直接观察 phase 是否仍有可继续并行派发的 lane。
- `host_runtime/sessions/*.json` 现在会补齐 `worker_id / worker_profile / preferred_worker_profile / tool_profile / allowed_tools / forbidden_paths / owned_paths / reuse_allowed / dispatch_kind / closure_policy / context_revision`，并内嵌 `session_card` 摘要。
- `host_runtime/mailboxes/*.jsonl` 已作为每个外部 worker session 的 mailbox 基础层落地；`session_created / session_updated` 事件会把状态变更、报告路径和下一步动作写进 mailbox。
- `build_host_runtime_summary(...)` 与 `commander_host_control.py status` 现在会额外暴露 `session_cards / session_pool`，让指挥官直接看到当前 worker lane 的写集合、复用资格和 mailbox 路径，而不是只看 `session_id + status`。
- 当前 `reuse_eligibility` 还是诊断合同，不代表 session 已经可脱离当前 task 直接复用；运行时会显式区分 `eligible_after_release` 与 `can_accept_new_task=false`，直到真正的 detached warm session pool 落地。
- `commander_host_runtime.py reuse-candidates` 现在可以按 `provider_id / worker_profile / tool_profile / allowed_tools / owned_paths` 查询“释放后可复用”的 host session，并返回拒绝原因与写集合 overlap；它是只读候选查询，不会启动窗口、不会释放 session，也不会把 active session 标成可直接接新任务。
- `commander_host_runtime.py release-reusable / release-task-reusable` 已提供显式释放入口：只有进入 `released_reusable` 的 session 才会把 `reuse_eligibility.decision` 提升为 `reusable_now`，并把 `can_accept_new_task` 置为 true；这一步仍不自动发送新任务，只提供 host runtime 可见状态转换。
- `commander_host_runtime.py assign-reusable` 现在可以把 `released_reusable` session 重新绑定到新 task，写入 `reuse_count / reused_from_task_id / task_history / dispatch_kind=reuse`，并在 mailbox 里追加 `assign_task` 事件；绑定后 session 回到 `waiting_worker`，所以不会继续显示为可接新任务。
- `ExternalWindowHostRuntimeAdapter.create_or_attach_session(...)` 现在会在 `reuse_allowed=true` 时优先查询 `released_reusable` 候选；如果匹配 provider / worker profile / tool profile / allowed tools / owned paths，就走 `assign-reusable` 复用旧 session，否则才创建新 session。
- `commander_host_runtime.py mailbox --commands-only` 现在可以读取单个 host session 的 mailbox 命令流；命令事件已覆盖 `assign_task / inspect_session / resume_session / stop_session`，worker 可以用 `after_sequence` 增量拉取。
- `commander_host_runtime.py ack-mailbox` 现在会记录 `mailbox_ack_sequence / mailbox_ack_at`，配合 `mailbox --unacked-only --commands-only` 可以避免 worker 重复消费同一条 `assign_task` 命令。
- `commander_host_runtime.py retry-mailbox` 现在会按 `mailbox_retry_sequence` 重新投递未 ack 命令，并保留 `retry_count / retry_of_sequence`，避免 worker 长时间未消费时只能靠聊天层手动重发。
- `assign-reusable` 的 session 与 mailbox `assign_task` 事件现在会携带 `context_delivery_mode=reuse_delta`、`context_delta_paths` 和 `context_paths_diff`，让复用窗口优先读增量/引用上下文入口，而不是把旧窗口当成全新窗口重灌。
- `tests/test_commander_graph.py::test_commander_graph_multi_worker_e2e_reuses_mailbox_and_closes` 已把 `2` 个并行 code task、`1` 个 local-script verifier lane、`inspect_session -> retry-mailbox -> ack-mailbox`、`release-reusable -> assign-reusable`、`context_paths_diff`、worker report ingest 与 session `close -> archive` 收进 graph 级 E2E 回归面。
- `ingest_worker` 现在会调用 `ingest_worker_report(...)`，把 report / archived report / improvement candidate / status 刷进 runtime，并用 graph `idempotency_key` 避免重复 ingest/candidate event。
- `run_until_handoff` 现在按 `host session -> attached report -> worker_report.json -> report.json` 的顺序发现可回收结果，并忽略 dispatch 预生成的 draft `worker_report.json`；发现真实结果后会先把 host session 标成 `report_ready`，ingest 后自动把关联 session 关到 `closed`。
- 外部等待超时后，`run_until_handoff` 会把当前 host session 标成 `resume_requested`，并把 `wait_monitor` / `host_wait` 诊断返回给 runner、stop gate 和 host control。
- `close_task` 现在会在 ingest 后检查 `ready_to_close`，满足条件时自动调用 `close_task(...)` 把生命周期推进到 `closed`。
- `archive_task` 现在会在 `closed` 后继续把任务推进到 `archived`。
- `user_handoff` 现在会在 `ready_for_user_delivery / pending_user` 时收敛成 graph-native `user_delivery`。
- 当前尚未完成的是外部 provider 的真实自动拉起和更完整 UI；但 `codex / claude-code / qwen / doubao` 已不再是空壳 `NotImplemented`，也不再只是“只吐 launch bundle 不托管”，可见宿主层也已有第一版 daemon 承载。

## Continuous Runner

新增 CLI：

- `python -m commander.graph.runners.run_until_handoff --thread-id <id>`
- `python -m commander.graph.runners.run_until_objective_handoff --thread-id <id>`

这个 runner 会把 graph 从“单次 invoke”推进到“持续续跑直到真实 handoff”：

- `continuation_mode=commander_internal`：继续 resume
- `continuation_mode=wait_external_result`：按超时参数轮询 host session、attached report、`worker_report.json` 和 `report.json`
- runtime 已有真实 `worker_report.json` 或 `report.json` 但本轮还没 ingest 时：自动捡起结果继续 ingest
- 只有 `user_handoff / terminal / waiting_external_result / paused_no_progress / max_rounds_exhausted` 才会停

新增 objective-level supervisor：

- `commander_objective_plan.py` + `commander_objective_plan.schema.json` 把“长期目标 -> 多 phase”也收成机器可读 backlog，而不是只留在人类任务卡
- `run_until_objective_handoff` 会在当前 phase 收口后自动检查 objective backlog；只要 objective 里还有 pending phase，就继续 promote 下一段，而不是把当前 `terminal` 误判成整条主线完成
- `stop_gate` 现在同时读取 phase backlog 和 objective backlog：phase 未清空时不会停，objective 未清空时也不会因为 phase 切换而停
- 真正允许 objective runner 停下的边界只有：`user_handoff / wait_external_result / paused_no_progress / max_objective_rounds_exhausted / objective terminal`
- 这条 objective 主链当前已经不再被“单 current_task 阻塞”完全锁死；只要 phase 里还有互不冲突的 ready goals，daemon 会先把并行槽位补满，再进入当前 objective round。

## Worker Provider

Codex 只是当前默认 worker provider，不是系统本体。后续 Claude Code、Qwen、豆包和 local-script 都通过 `adapters/worker_providers/` 接入统一合同：

- 输入统一 `task packet`
- 遵守 `tool_profile / allowed_tools / forbidden_paths`
- 声明 capability
- 输出统一 `worker_report`
- 返回 `done / blocked / need_split`

## Provider Governance Notes

- Phase 5.9 adds an explicit provider registry instead of growing more `if/else` wiring.
- The registry records provider metadata such as `provider_id`, label, capabilities, lifecycle support, supported dispatch kinds, and supported tool profiles.
- Dispatch now runs a preflight governance check before host-session creation or inline provider execution.
- Governance rejects capability/profile mismatches, unknown providers, unknown tool profiles, and allowed tools that exceed the declared tool profile.
- The governance layer now emits machine-readable `tool_policy` and `path_policy` snapshots, so accepted and rejected dispatches both carry a structured explanation of the execution surface.
- `owned_paths` and `forbidden_paths` are now checked together. If a requested write scope overlaps a protected path boundary, dispatch is rejected before worker launch.
- Accepted `external_window` dispatches now push the same governance contract into both the human launch prompt and the machine-readable `launch_bundle`, so an external worker can see `tool_profile / allowed_tools / forbidden_paths / owned_paths` without reopening hidden state first.
- `ingest_worker_report(...)` now re-checks `changed_files` against the task packet. Reports that touch `forbidden_paths` or escape declared `owned_paths` are rejected before they can advance lifecycle state.
- `forbidden_paths` and `owned_paths` remain contract boundaries. The governance layer can surface and block unsafe combinations, but it does not claim to be a filesystem sandbox.

## Context Routing

Milestone 2 的 host/runtime 集成前置层已经补上第一版自动上下文路由：

- `commander_context_router.py` 会根据 `task packet + provider_id + runtime artifacts` 生成 `context_bundle.json`
- bundle 当前是“注册表驱动 + 关键词/显式 tag 路由”，还不是插件式 provider 发现
- `context_bundle.json` 现在会显式带出 `read_policy`，把默认读取顺序固定成 `worker_brief -> packet -> context_bundle -> resume_anchor -> checkpoint`
- 每个 routed entry 现在都会带 `disclosure_mode / summary_lines / paths / deferred_paths / when_to_open`
- `worker_brief.md` 与 `external_window` launch prompt 现在都会把这套 metadata-first 规则显式展示给执行窗口：先看摘要和必读入口，只在当前切片真的需要更深背景时才展开 `deferred_paths`
- `status.json / checkpoint.json / resume_anchor.json` 现在还会附带 `context_budget` 估算：给出这轮 `open_now / deferred / full_expand` 的预计 token 与相对预算占比；它是 repo/runtime 侧的启发式估算，不是 Codex 客户端真实计费
- `commander_context_router.py` 现在不只做估算，还会做 budget-aware routing：entry 会显式带 `priority / budget_behavior / budget_action / budget_reason`，并在 router 预计 `open_now` 超过 `round_budget_tokens` 时，把低优先级 open paths 自动移入 `deferred_paths`；同一批被预算挡住的 `context_id` 会写回 `read_policy.deferred_by_budget_context_ids` 与 `context_budget.entries_deferred_by_budget`，`commander_status.py` 也会把它压成 `context_route_summary`
- 当前动态的是“给 worker 装哪些上下文”，不是“自动 import 哪个 provider 模块”

一句话记忆：

**我们现在已经有了动态上下文装配 + 渐进式披露，但 provider 发现机制仍然是静态注册。**
