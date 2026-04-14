# 指挥官 harness v1 实施优先级

更新时间：2026-04-11

这份文档回答的是：

**如果当前仓库要把“指挥官系统”往真正可执行的 harness 再推进一小步，最合理的实现顺序是什么。**

它不是最终架构图，也不是执行窗口任务单全文。

它当前应视为外圈专题文档：

- 负责记录 harness v1 当时的推进顺序和边界
- 不负责定义指挥官系统本体
- 如果与 `指挥官任命.md`、`指挥官文档.md` 冲突，始终以前两者为准

---

## 1. 先给结论

当前最稳的推进顺序是：

1. 先补 transport
2. 再补确定性验证
3. 再补最小可观测性
4. 最后才考虑更强自动化

翻成当前仓库语言就是：

1. 先把 `dispatch / ingest / status` 做出来
2. 先让 task packet 和 task report 变成结构化合同
3. 先让执行窗口结果稳定回到指挥官
4. 暂时不要直接跳到多 worker 并行、自动续派、自动开窗

---

## 2. 为什么是这个顺序

视频里最有价值的提醒不是“多 agent 更强”，而是：

1. 立刻能做的，是规则和入口
2. 中期最该补的，是确定性验证层和基础可观测性
3. 长期才是模块化、可替换的 harness 架构

对当前仓库来说，这个顺序刚好对应：

1. 第一阶段已经有一部分：
   - `AGENTS.md`
   - `commander/core/任命.md`
   - `commander/core/主文档.md`
   - `commander/outer/新窗口启动指令模板.md`
   - `commander/transport/prompts/execution_window_task_template.md`
2. 当前真正缺的是第二阶段的入口：
   - 结构化任务合同
   - 结构化结果回收
   - 状态查看
   - 基础验证
3. 现在还不适合直接跳第三阶段：
   - 自动多窗口调度
   - 大而全状态机
   - 第二套长期记忆层

---

## 3. v1 的推荐分阶段顺序

### 3.1 Phase A：锁定边界

目标：

- 先明确 v1 做什么、不做什么

这一阶段必须固定的事实：

1. 核心链路是：
   - `用户 -> 指挥官 -> 执行窗口 -> 指挥官 -> 用户`
2. 文档仍是真相源
3. harness 只补 transport，不复制长期记忆骨架
4. 执行窗口是 worker，不直接面向用户

完成标志：

- 这些边界已经写进稳定文档
- 新执行窗口不需要再靠聊天补口径

当前状态：

- 已基本完成

---

### 3.2 Phase B：先做结构化合同

目标：

- 定义最小 machine-readable handoff 合同

建议优先做：

1. `commander/transport/schemas/commander_task_packet.schema.json`
2. `commander/transport/schemas/commander_task_report.schema.json`

task packet 至少要有：

- `task_id`
- `title`
- `goal`
- `must_read`
- `bounds`
- `validation`
- `forbidden_paths`
- `report_contract`
- `status`

task report 至少要有：

- `task_id`
- `status`
- `summary`
- `changed_files`
- `verification`
- `commit`
- `risks`
- `recommended_next_step`
- `needs_commander_decision`

完成标志：

1. schema 能被本地脚本读取
2. 至少有 1 组合法样例和 1 组非法样例
3. 状态值至少覆盖：
   - `done`
   - `blocked`
   - `need_split`

为什么这一层优先级最高：

- 因为没有合同，后面的 dispatch / ingest 只能继续拼长 prompt

---

### 3.3 Phase C：再做 dispatch

目标：

- 让指挥官能把任务稳定压成 packet 和 worker brief

建议优先做：

1. `commander/transport/scripts/commander_dispatch.py`

最小职责：

1. 接收任务输入
2. 产出 task packet
3. 产出给执行窗口的最小 worker brief
4. 把运行时产物写到 `.runtime/commander/`

最小不要做：

1. 不自动开窗口
2. 不自动决定复杂拆分
3. 不替代指挥官判断边界

完成标志：

1. 能在临时 runtime 目录产出 1 个有效 packet
2. packet 能通过 schema 校验
3. 生成的 brief 能直接被指挥官复制给执行窗口

---

### 3.4 Phase D：再做 ingest 和 status

目标：

- 让 worker 结果能结构化回到指挥官

建议优先做：

1. `commander/transport/scripts/commander_ingest.py`
2. `commander/transport/scripts/commander_status.py`

ingest 最小职责：

1. 读取 task report
2. 做 schema 校验
3. 输出给指挥官可直接阅读的回收摘要
4. 不直接改 `commander/core/主文档.md` 或 `commander/state/时间线.md`

status 最小职责：

1. 查看当前 task / report / event 状态
2. 能区分未开始、已派发、已回报、阻塞

完成标志：

1. dispatch -> report -> ingest 最小 smoke 能跑通
2. status 能看到当前任务状态
3. 指挥官不再需要手工翻多个文件判断任务有没有回报

---

### 3.5 Phase E：补确定性验证和基础可观测性

目标：

- 不只“能跑”，还要“能校验、能追踪、能归因”

建议优先做：

1. `tests/test_commander_harness.py`
2. CLI smoke
3. 最小 event log

最小验证包括：

1. schema 校验测试
2. dispatch CLI smoke
3. ingest CLI smoke
4. status CLI smoke
5. 非法输入失败路径测试

最小可观测性包括：

1. `task_id`
2. `run_id`
3. 状态变化时间点
4. 失败原因

为什么这一步排在 transport 后面：

- 因为先要把 handoff 结构固定下来，验证和观测才不会失焦

---

## 4. 当前明确不做什么

至少在 v1，不做下面这些：

1. 不做多 worker 并行编排
2. 不做自动续派
3. 不做自动归档到所有文档
4. 不做第二套 `plans / memory / reports / debt`
5. 不把执行窗口升级成直接和用户交互的长期代理
6. 不把 `spawn_agent` 当成 v1 的前置条件

原因不是这些永远不做，而是：

- 现在先做它们，会把复杂度和误差一起放大

补充说明：

- 这条“不把 `spawn_agent` 接进第一版主路径”描述的是 v1 的历史落地顺序
- 当前 v1 transport 已落地后，指挥官已经可以把子执行 agent 作为默认执行载体叠在这层 transport 之上
- 也就是说：`spawn_agent` 现在可以用，但它不是当初 v1 成立的前提

---

## 5. 什么时候再考虑更强自动化

只有当下面几条都满足时，才适合考虑下一步：

1. `dispatch / ingest / status` 已稳定
2. 至少一类真实任务已经通过 v1 跑通
3. 指挥官回收成本确实下降
4. 阻塞结果能够稳定回指挥官，而不是继续长跑
5. 能清楚区分：
   - 适合自动续派的情形
   - 必须停下来等指挥官判断的情形

在那之前，宁可保持人工开窗，也不要过早把复杂调度自动化。

---

## 6. 对当前任务卡的直接含义

如果下一轮要真实推进 `dispatch + ingest harness v1`，最合理的派工顺序是：

1. 先做 schema
2. 再做 dispatch
3. 再做 ingest 和 status
4. 最后补测试和最小 event log

不要反过来从“自动开窗”开始做。

一句话收口：

**当前仓库的 harness v1，应该先把 handoff 做稳，再把自动化做强。**
