# 指挥官系统吸收 DeepAgents 落地清单

更新时间：2026-04-13

## 1. 这份清单解决什么

这份文档不是要把 `D:\Develop\deepagents` 整体搬进当前仓库。

它解决的是另一个更具体的问题：

- `deepagents` 里哪些能力已经证明是成熟工程接口
- 哪些能力适合吸收到当前“指挥官 + LangGraph + Harness + Hermes”系统里
- 哪些不该照搬
- 真要落地时，应该按什么顺序推进，才不会又变成“今天吸一点、明天补一点”的碎片化施工

一句话定义：

**把 `deepagents` 当成上游模式库，不把它当成当前系统的替代宿主。**

---

## 2. 基线判断

当前仓库已经有这些能力：

1. `LangGraph` 级状态机、resume、stop gate、objective/phase backlog
2. `packet -> worker_report -> ingest -> close/archive` 的结构化 transport
3. `host runtime / daemon / mailbox / reusable session / context bundle`
4. 受控学习循环：`candidate -> review -> apply -> archive`
5. repo truth source、问题索引、时间线、任务卡、skill-source 分层

因此当前问题不是“缺一个 agent 框架”。

真正的问题是：

1. 压缩后的恢复事件还不够强
2. tool/profile/path 治理还没形成更硬的 middleware 层
3. skill source 仍偏事实存在，缺少统一注册与覆盖规则
4. 学习闭环已有审批链，但还没有 `better-harness` 式离线实验场

---

## 3. 吸收边界

### 3.1 明确要吸收的部分

1. **中间件栈显式化**
   - 把能力组合写成 machine-readable 运行时栈，而不是散落在 prompt、脚本和口头约束里
2. **技能源分层与渐进披露**
   - skill 先注入 metadata，再按需读取全文
   - 多 source 按优先级覆盖，避免 skill 装载规则继续隐式化
3. **压缩恢复事件**
   - 不只是“对话总结”
   - 要把 compact / offload / resume 变成 runtime 可验证事件
4. **工具权限硬约束**
   - 把 `allowed_tools / forbidden_paths / owned_paths` 从合同字段升级成执行期硬限制
5. **离线 harness 优化实验场**
   - 把 prompt / tool / skill / middleware / wiring 作为可编辑 surface
   - 用 `train / holdout / scorecard` 判定是否值得升级为候选

### 3.2 明确不吸收的部分

1. 不把 `deepagents` CLI / TUI 直接当当前系统宿主
2. 不采用它偏 “trust the LLM” 的默认安全模型
3. 不允许 memory/skill 自动直接改 live truth source
4. 不把它的目录骨架原样复制到当前仓库

---

## 4. 和当前系统的一一对应

### 4.1 Runtime 组装层

`deepagents` 对应做法：

- `create_deep_agent(...)` 把 `todo / skills / filesystem / subagents / summarization / memory / HITL / permissions` 组装成固定中间件栈

当前系统对应落点：

- `commander/graph/`
- `commander/transport/scripts/`
- `commander/outer/指挥官LangGraph运行时项目化方案.md`

当前缺口：

- 当前已有 orchestration，但“运行时治理层”的顺序和职责还不够显式
- 还没有统一表达：
  - 哪些是 prompt 层
  - 哪些是 context 层
  - 哪些是 permission/governance 层
  - 哪些是 learning 层

### 4.2 Skills 分层加载

`deepagents` 对应做法：

- skills 多 source 加载
- 同名 skill 后者覆盖前者
- system prompt 只先注入技能列表和路径
- 需要时再读 `SKILL.md`

当前系统对应落点：

- `commander/skill-source/`
- `C:\Users\26877\.codex\skills\...`
- `commander/transport/scripts/commander_memory_index.py`
- `context_bundle.json / worker_brief.md / external_window launch prompt`

当前缺口：

- 已把执行入口侧上下文升级成 metadata-first：`context_bundle` 现已显式带 `read_policy / summary_lines / deferred_paths / when_to_open`，执行窗口默认先读摘要和必读入口，再按需展开
- 已有 repo skill、本地 skill、问题索引和 skill 候选升级链
- 但还缺统一的 `skill registry / source precedence / load policy`

### 4.3 Compact / Resume 事件

`deepagents` 对应做法：

- `_summarization_event`
- `/conversation_history/{thread_id}.md`
- resumed thread compact integration test

当前系统对应落点：

- `.runtime/commander/*`
- `status.json / checkpoint.json / resume_anchor.json`
- `commander_host_daemon.py`
- `run_until_handoff`

当前缺口：

- 当前能 resume，但还没有一条明确的“压缩事件 ledger”
- 上下文压缩之后能否继续，仍带有对聊天层承接质量的依赖

### 4.4 Permissions Middleware

`deepagents` 对应做法：

- `FilesystemPermission`
- first-match-wins
- allow/deny
- pre-check + post-filter

当前系统对应落点：

- `task packet` 里的 `allowed_tools / forbidden_paths / owned_paths`
- provider/tool profile
- host runtime/worker governance

当前缺口：

- 当前更多是“合同里声明边界”
- 还没有把这些边界统一做成 provider 执行前后的硬 enforcement

### 4.5 Better Harness 实验场

`deepagents` 对应做法：

- outer agent / inner agent
- editable surfaces
- `train / holdout / scorecard`
- keep/discard candidate

当前系统对应落点：

- `improvement candidate`
- `skill candidate`
- review/apply/archive 流程

当前缺口：

- 当前更像“任务完成后提案”
- 还不是“有实验设计、有分层 surface、有留存判据”的离线优化系统

---

## 5. 分阶段落地方案

这里不是可选菜单，而是推荐执行顺序。

### Phase A：Compact / Resume Ledger

目标：

- 解决“上下文压缩后承接看运气”的问题

当前状态：

- 已完成第一轮正式落地
- 当前已形成的稳定事实：
  - task runtime 显式拥有 `compactions/` 与 `compaction_event.json`
  - `run_until_handoff` 会在真实 task handoff 边界写入 compact artifact 与最新恢复事件
  - `run_until_objective_handoff` 会在 objective handoff 边界写入带 `objective_id / final_objective_summary` 的 compact 事件
  - `commander_resume.py` 默认优先读取 `compaction_event.json`
  - 回归已覆盖 `run_until_handoff / run_until_objective_handoff / commander_resume`

要落地的内容：

1. 在 commander runtime 里引入显式 `compaction_event`
2. 把被压缩的长历史落到独立 artifacts 路径，而不是只留聊天摘要
3. 让 `resume` 先读 `compaction_event`，再决定恢复入口
4. 为 compact/resume 补 integration 级测试

建议产物：

1. `commander/graph` 下新增 compact/resume adapter 或 policy
2. `.runtime/commander/...` 下新增 compact history artifact
3. `tests/` 下新增 resumed-thread compact E2E

完成判据：

1. 压缩后恢复不再只依赖聊天承接
2. compact 历史有明确 artifact 和事件记录
3. 重启或换窗口后，能通过 event 恢复正确入口

### Phase B：Tool / Path Governance Middleware

目标：

- 把治理从“声明式边界”升级成“执行期硬限制”

当前状态：

- 已完成第一刀结构化治理落地
- 当前已形成的稳定事实：
  - worker provider governance 现已产出 machine-readable `tool_policy / path_policy`
  - `owned_paths` 与 `forbidden_paths` 的明显重叠会在 dispatch 前被拒绝
  - 通过的 dispatch 也会把治理快照带进 `worker_dispatch` 与 host session `session_card.governance`
  - `external_window` 的 launch prompt 与 `launch_bundle` 现在也会显式带出 `tool_profile / allowed_tools / forbidden_paths / owned_paths / governance`，执行窗口入口不再只靠 packet/隐藏状态补全约束
  - `ingest_worker_report(...)` 现在会把 `changed_files` 和 packet 的 `forbidden_paths / owned_paths` 对齐，越界 report 会在回收侧被拒收
  - `context_bundle` 现已补上 `read_policy / summary_lines / deferred_paths`，执行窗口入口不再默认整批打开上下文，而是按需展开
  - `context_router` 现已进入 budget-aware 模式：routed entry 会显式带 `priority / budget_behavior / budget_action / budget_reason`，并在默认 `round_budget_tokens` 下把 `memory_index / langgraph_runtime / repo_runbook / execution_workbench` 这类低优先级重文档自动转入 `deferred_paths`；`read_policy` 与 `context_budget` 会同步暴露 `deferred_by_budget_context_ids`
  - inline provider 返回 `worker_report` 后、进入 ingest 前，现在会先走 graph 层 `result_post_check`：`changed_files` 越过 `forbidden_paths / owned_paths`，或 read-only / no-write-intent provider 报告了写入结果时，都会被标记为 `provider_result_governance_rejected` 并停止回写，ingest 侧校验保留为第二道防线；`local-script` 还会用 git status before/after 探测未声明的 repo 变更，并把新增变更并入 `changed_files` 后再进入同一条 post-check

要落地的内容：

1. 明确 `tool_policy / path_policy / write_ownership_policy`
2. provider 执行前做 preflight deny
3. provider 执行期与结果回写前做更强的 post-check/filter
4. 对 `external_window / local-script / future providers` 统一治理

建议产物：

1. `commander/graph/policies/` 下新增 tool/path governance 层
2. `worker provider` 统一接入 policy gate
3. 补 deny/allow/reject 回归

完成判据：

1. `allowed_tools / forbidden_paths / owned_paths` 真正可执行
2. provider 不能绕过治理层直接运行高风险动作
3. 结果中出现越界 artifact 时会被显式拦截或标红

### Phase C：Skill Registry 与 Source Precedence

目标：

- 把 repo skill、本地 skill、候选 skill 的装载和优先级做成系统能力

要落地的内容：

1. 定义 `skill_source_registry`
2. 明确 source 优先级：
   - repo truth-source shell
   - local installed skill
   - candidate skill
3. 默认只先注入 metadata，不默认注入技能全文
4. skill 命中后再按需读取 `SKILL.md`

建议产物：

1. `commander_memory_index` 扩展为 registry-aware 检索
2. skill load policy 文档
3. 候选 skill 与 live skill 的隔离规则

完成判据：

1. 指挥官能解释某个 skill 为什么命中、来自哪个 source
2. 候选 skill 不会覆盖 live skill
3. skill 使用从“靠记忆”变成“靠 registry + load policy”

当前落地状态：

- `commander_memory_index` 已扩展为 registry-aware skill 检索，payload 会输出 `skill_source_registry`，并登记 `repo_skill_source / local_skills / candidate_skills` 三类来源。
- skill source 优先级已固化为 `repo_skill_source > local_skills > candidate_skills`；同名 skill 会把 repo truth-source 标记为 effective source，本地副本标记为 shadowed，candidate 始终 `candidate_can_override_live=false`。
- skill 检索默认 metadata-first，只索引 skill metadata 与 `load_target`，不把 `SKILL.md` 正文灌入 memory index。
- `commander_skill_load.py` 已补显式按需加载入口：默认只返回加载计划，只有传入 `--include-body` 才读取对应 `SKILL.md` 正文；candidate source 只能作为 review-only 来源显式选择。
- [指挥官SkillRegistry与加载策略.md](/D:/Develop/Python-Project/Agent/commander/outer/%E6%8C%87%E6%8C%A5%E5%AE%98SkillRegistry%E4%B8%8E%E5%8A%A0%E8%BD%BD%E7%AD%96%E7%95%A5.md) 已作为 Phase C 的 load policy 文档，并纳入 memory index 的 persistent doc source。

### Phase D：Better-Harness 风格离线实验场

目标：

- 让系统具备“可控优化 harness surface”的离线实验能力

要落地的内容：

1. 定义 editable surfaces：
   - prompt constitution
   - routing/context policy
   - skill shell
   - middleware wiring
   - tool governance config
2. 定义 `train / holdout / scorecard`
3. 候选只在 proposer workspace 里改
4. 只有分数提升才进入 candidate review

建议产物：

1. `commander/experiments/` 或等价目录
2. experiment config schema
3. keep/discard report

完成判据：

1. 至少 1 组 surface 能跑 baseline vs candidate
2. 有明确 keep/discard 证据
3. 结果进入现有 `candidate -> review -> apply` 链，而不是旁路上线

当前落地状态：

- 已新增 `commander_experiment.py` 作为离线 experiment runner；它读取 experiment config，比较 baseline / candidate 在 `train / holdout` scorecard 上的平均分，并输出 `keep / discard` 报告。
- 已新增 `commander_experiment_config.schema.json`，第一版 surface 覆盖 `prompt_constitution / routing_context_policy / skill_shell / middleware_wiring / tool_governance_config`。
- candidate 必须显式位于 proposer workspace；runner 不修改 live surface，只在 keep 时生成候选源报告。
- holdout 分数超过阈值时，runner 复用既有 `commander_propose_improvement.build_candidate(...)` 写入 `.runtime/commander/improvements/<task_id>.candidate.json`，继续进入现有 review/apply/archive 链；未达标时只写 discard report。

---

## 6. 推荐执行顺序

默认顺序：

1. `Phase A` 先做 compact/resume ledger
2. `Phase B` 再做 tool/path governance middleware
3. `Phase C` 再做 skill registry
4. `Phase D` 最后做 better-harness 离线实验场

原因：

1. `Phase A` 先解决当前真实痛点：压缩后容易断
2. `Phase B` 先把安全边界收硬，不然后面引入更多 runtime 能力只会放大风险
3. `Phase C` 让 skills 真正工程化，而不是继续半手工
4. `Phase D` 依赖前 3 层先收成稳定 surface，才值得做实验优化

---

## 7. 当前不该做的事

1. 不要把 `deepagents` 整个 vendoring 进仓库
2. 不要为了“像 deepagents”而改掉现有 truth-source 文档体系
3. 不要把 memory 自动写回 repo 主文档
4. 不要跳过候选审批链，直接让实验结果覆盖 live prompt/skill/policy

---

## 8. 下一执行入口

如果按当前系统真实优先级推进，下一步最合理的不是回头重做 `Phase A`，而是直接进入：

**`Phase B：Tool / Path Governance Middleware`**

建议第一刀：

1. 先盘出现有 `provider governance / tool profile / ownership / forbidden_paths` 的真实执行点
2. 明确 `tool_policy / path_policy / write_ownership_policy` 的统一运行时接口
3. 先补一条 deny/allow integration 验收，再把治理从 preflight 继续收紧到执行期

这一步完成后，再继续 `Phase C`。

---

## 9. 和主方案的关系

这份清单是：

- `commander/outer/指挥官LangGraph运行时项目化方案.md` 的补充执行清单
- `deepagents` 外部方法吸收的边界文件

它不是：

- 新的总方案
- 新的长期记忆主文档
- 替代当前里程碑的平行路线图

一句话边界：

**主方案定义“我们最终要成为什么”，这份清单定义“从 `deepagents` 里具体吸什么、按什么顺序吸”。**
