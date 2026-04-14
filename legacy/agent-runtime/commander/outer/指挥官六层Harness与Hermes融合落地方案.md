# 指挥官六层 Harness 与 Hermes 融合落地方案

更新时间：2026-04-12

## 1. 目标

这份方案解决一件事：

把“六层 Harness 骨架”和 Hermes 的“受控进化能力”融合成当前指挥官体系的下一条可执行主线，而不是再并排增加一套新框架。

一句话说：

**六层 Harness 负责让系统稳定，Hermes 增强件负责让系统在稳定前提下持续变强。**

---

## 2. 总边界

本方案允许吸收的内容：

1. 六层 Harness 的分层检查法：
   - 上下文边界层
   - 工具系统层
   - 执行编排层
   - 记忆与状态层
   - 评估与观测层
   - 约束校验与恢复层
2. Hermes 的四个增强点：
   - 三层记忆
   - 受控学习循环
   - skill 候选升级
   - 工具 / 子 agent 最小权限

本方案明确不做：

1. 不再造第二套平行骨架，不复制 `plans / memory / reports / debt`
2. 不自动改 live skill
3. 不把所有聊天灌进长期记忆
4. 不先上复杂 LangGraph 平台化编排
5. 不把“常驻 worker”做成无限累积上下文的长寿 agent

一句话规则：

**永久的是角色、权限和外部状态，不是无限膨胀的隐式上下文。**

---

## 3. 当前基础

当前仓库已经具备的能力：

1. 上下文边界层：
   - `commander/core/任命.md`
   - `commander/core/主文档.md`
   - `commander/state/当前任务卡.md`
   - `packet / checkpoint / report / status`
2. 工具系统层：
   - `tool_profile / allowed_tools`
   - `commander/transport/scripts/commander_dispatch.py`
   - `commander/transport/scripts/commander_harness.py`
3. 执行编排层：
   - 指挥官 -> 子执行 agent -> ingest/status
   - `controller_handoff`
   - `conversation_stop_required`
4. 记忆与状态层：
   - 三层记忆 v1
   - `commander_memory_search.py`
   - `.runtime/commander/*`
   - `commander/state/*`
5. 评估与观测层：
   - `self_check.ps1`
   - `run_delivery_checks.py`
   - `events.jsonl`
   - `worker_report / report / checkpoint`
6. 约束校验与恢复层：
   - schema
   - draft guard
   - `commander_resume.py`
   - 子 agent 回收护栏

当前最明显的缺口：

1. 执行编排层还没有 warm worker pool，子执行 agent 启动成本偏高
2. 记忆与状态层仍在推进 `.runtime -> Redis / SQL / 文件层` 分层
3. 学习循环还没有自动接到真实任务回收之后
4. 工具权限目前还是“合同可见”，还不是平台硬约束

---

## 4. 融合映射

### 4.1 六层 Harness 作为静态骨架

1. 上下文边界层回答：
   - 任务是谁做
   - 做到哪
   - 成功标准是什么
2. 工具系统层回答：
   - 能用什么工具
   - 什么时候该调
   - 结果怎么收敛
3. 执行编排层回答：
   - 谁拆任务
   - 谁执行
   - 谁验证
   - 谁回收
4. 记忆与状态层回答：
   - 当前状态是什么
   - 历史事实放哪
   - 恢复锚点在哪
5. 评估与观测层回答：
   - 结果好不好
   - 失败为什么
   - 哪些值得沉淀
6. 约束校验与恢复层回答：
   - 哪些不能做
   - 输出前后怎么校验
   - 失败后如何恢复

### 4.2 Hermes 作为动态增强件

1. 三层记忆挂到“记忆与状态层”
2. 学习循环挂到“评估与观测层”
3. skill 候选升级挂到“评估与观测层 -> 约束校验层”的闸门之间
4. tool profile / worker profile 挂到“工具系统层 + 执行编排层”

一句话收口：

**六层是结构，Hermes 是进化回路。**

---

## 5. 总体推进顺序

当前固定按 6 个阶段推进：

1. `Phase 0`：冻结融合计划
2. `Phase 1`：执行编排层补齐 warm worker pool v1
3. `Phase 2`：记忆与状态层分层落地
4. `Phase 3`：评估与观测层接学习循环
5. `Phase 4`：约束校验与恢复层收紧
6. `Phase 5`：真实任务试跑与归档

默认规则：

1. 一次只推进一个 Phase
2. 每个 Phase 都要有产物、验证、完成判据
3. 每个 Phase 验收通过后，默认进入下一阶段
4. 除非出现真实阻塞、需要用户拍板或阶段整体收口，否则不回到“要不要继续”的聊天模式

---

## 6. Phase 0：冻结融合计划

目标：

- 把“六层骨架 + 四个增强点 + 推进顺序”写进外部真相源

产物：

1. 本方案文档
2. `commander/state/当前任务卡.md` 中的活跃主线

完成判据：

1. 新窗口接手时，不需要再从聊天里猜“这条融合主线下一步是什么”
2. 当前 Phase、下一步最小动作、停止条件都能从任务卡恢复

---

## 7. Phase 1：执行编排层补齐 warm worker pool v1

目标：

- 把“每次新开一次性窗口”升级成“预热 + 复用的专职 worker”

产物：

1. `commander/transport/schemas/commander_worker_slot.schema.json`
2. `commander/transport/scripts/commander_worker_pool.py`
3. packet schema 增补字段：
   - `worker_profile`
   - `preferred_worker_profile`
   - `reuse_allowed`
4. `commander/outer/指挥官warm worker池说明.md`

默认 worker profile：

1. `code-worker`
2. `verifier-worker`

边界：

1. 只做 warm pool，不做复杂多 worker 图编排
2. 常驻的是 worker profile，不是无限上下文
3. 同一条任务链可复用 worker，但当前任务仍以 `packet / checkpoint` 为真相源

完成判据：

1. 至少两类 worker profile 可以被 acquire / reuse / release
2. 指挥官能看见 worker 当前状态：
   - `warm_idle`
   - `busy`
   - `completed_waiting_close`
   - `closed`
3. 同一条连续任务链至少有一次复用成功，而不是每轮都重新 spawn

---

## 8. Phase 2：记忆与状态层分层落地

目标：

- 把 Hermes 的三层记忆正式压进六层中的“记忆与状态层”
- 同时推进 `.runtime` 分层迁移

与当前主线的关系：

1. `5.3 运行时存储分层迁移` 直接并入本阶段
2. 不单开平行主线，不重复计划

产物：

1. 会话恢复分层落地：
   - session 元数据归属明确
   - 文件正文与 SQL 元数据边界明确
2. 指挥官 harness 分层落地：
   - task / checkpoint / report 元数据可索引
3. `commander_memory_search.py` 扩展到优先利用元数据层

边界：

1. 不一次性把所有 `.runtime` JSON 数据库化
2. 不把 report / trace / candidate 正文全塞进 SQL
3. `.runtime` 的目标是降级为缓存 / 调试层，而不是立即消失

完成判据：

1. 会话恢复不再只靠扫目录
2. 指挥官恢复不再只靠遍历 `.runtime/commander/tasks/*`
3. `.runtime` 每个大类目录都有明确目标归属

---

## 9. Phase 3：评估与观测层接学习循环

目标：

- 让真实任务回收后自动产出 improvement candidate

产物：

1. `commander_propose_improvement.py` 与 ingest 链接通
2. `report -> improvement candidate` 的最小触发规则
3. `commander/outer/指挥官学习循环提案说明.md` 更新为真实任务口径

边界：

1. 只做自动提案，不自动写回文档
2. 只做候选分流，不自动启用 skill
3. 观测层优先相信验证证据，不相信自评

完成判据：

1. 至少一条真实任务在回收后自动产出 improvement candidate
2. candidate 能明确指向：
   - 文档
   - 脚本
   - skill 候选

---

## 10. Phase 4：约束校验与恢复层收紧

目标：

- 把当前“可见约束”进一步收紧成“更难忘、可恢复、可拒绝错误输入”的控制面

产物：

1. tool profile 校验进一步收紧
2. worker 回收与 TTL 规则显式化
3. 恢复链补充：
   - worker pool 恢复
   - 当前 handoff 恢复
   - pending close worker 提醒
4. `commander/outer/指挥官调度与结果回收harness-v1.md` 或对应文档更新

边界：

1. 仍然不做平台级硬沙箱
2. 仍然不做自动 live skill 生效
3. 继续坚持“默认继续，例外才停”

完成判据：

1. 工具边界、worker 状态、恢复锚点都能从外部状态看见
2. 即使上下文压缩，也不再主要依赖聊天记忆恢复执行状态

---

## 11. Phase 5：真实任务试跑与归档

目标：

- 用真实任务验证这套融合主线承载业务，而不是只会修系统自己

产物：

1. 至少 2 次真实任务试跑记录
2. 时间线归档节点
3. 必要时产出 improvement candidate 或 skill candidate

完成判据：

1. warm worker pool 至少承载过 1 条真实任务链
2. 记忆与状态层至少承载过 1 条真实恢复链
3. 学习循环至少对 1 条真实任务给出候选提案

---

## 12. 停止条件

只有出现下面情况，才允许暂停默认继续：

1. 需要用户拍板
2. 出现真实技术阻塞
3. 当前 Phase 已整体收口，且不存在清楚的下一步最小动作

如果不满足这三条，默认继续推进当前 Phase 的下一刀或下一个 Phase。

---

## 13. 当前推荐执行口径

从本方案生效后，默认执行顺序是：

1. 先完成 `Phase 0`
2. 直接进入 `Phase 1：warm worker pool v1`
3. `Phase 1` 验收通过后，再进入 `Phase 2`
4. `Phase 2` 内直接承接当前的 `5.3 运行时存储分层迁移`

一句话收口：

**先补执行编排层的 warm worker 池，再继续落记忆与状态层；这样既解决你当前的新窗口启动成本，也不会把现有 `.runtime` 分层主线丢掉。**
