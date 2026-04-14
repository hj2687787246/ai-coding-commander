# 指挥官 Hermes-lite 受控进化方案

更新时间：2026-04-11

## 1. 目标

这份方案只解决一件事：

把 Hermes Agent 里对当前仓库最有价值的能力，按当前指挥官体系的边界吸收进来，并且让后续推进不再靠聊天临时起意。

一句话说：

**做“受控进化”，不做“放养进化”。**

---

## 2. 总边界

本方案允许吸收的方法：

1. 三层记忆
2. 记忆检索
3. 学习循环
4. skill 候选升级
5. tool profile / 最小权限

本方案当前不做的事：

1. 不自动启用 live skill
2. 不自动改写仓库事实文档
3. 不复制 `plans / memory / reports / debt` 平行骨架
4. 不把所有聊天灌进长期记忆
5. 不做 cron 自运行
6. 不做多 worker 并行编排
7. 不让子执行 agent 直接面向用户

一句话规则：

**自动产出改进提案，但是否吸收，由指挥官按证据决定。**

---

## 3. 总体推进顺序

当前固定按 6 个阶段推进：

1. `Phase 0`：冻结计划
2. `Phase 1`：记忆检索层
3. `Phase 2`：学习循环提案层
4. `Phase 3`：skill 候选升级链
5. `Phase 4`：tool profile / 最小权限
6. `Phase 5`：真实任务试跑与归档

默认规则：

1. 一次只推进一个 Phase
2. 每个 Phase 都要有可验证产物
3. 每个 Phase 验收通过后，才进入下一阶段
4. 除非出现真实阻塞、需要用户拍板或阶段整体收口，否则默认继续

---

## 4. Phase 0：冻结计划

目标：

- 把这条主线的边界、阶段、产物、停止条件写进外部真相源

产物：

1. 本方案文档
2. `commander/state/当前任务卡.md` 中的活跃主线

完成判据：

1. 新窗口接手时，不需要再从聊天里猜“下一步是什么”
2. 当前 Phase 和下一步最小动作能从任务卡直接恢复

---

## 5. Phase 1：记忆检索层

目标：

- 给现有指挥官真相源补一个 repo-native 的检索入口

产物：

1. `commander/transport/scripts/commander_memory_search.py`
2. `tests/test_commander_memory_search.py`
3. `commander/outer/指挥官记忆检索说明.md`

检索范围：

1. `commander/state/当前任务卡.md`
2. `commander/state/时间线.md`
3. `commander/state/问题索引.md`
4. `commander/core/主文档.md`
5. `.runtime/commander/tasks/*/checkpoint.json`
6. `.runtime/commander/tasks/*/report.json`
7. `.runtime/commander/tasks/*/worker_report.json`
8. `.runtime/commander/tasks/*/status.json`

边界：

1. 检索层只搜索现有真相源
2. 检索结果不成为新的真相源
3. v1 先做轻量 repo-native 检索，不先引入第二套独立记忆数据库

完成判据：

1. 能回答“上次做到哪了”
2. 能回答“类似问题之前出现在哪”
3. 能返回可读路径和摘录，而不是只给模糊命中

---

## 6. Phase 2：学习循环提案层

目标：

- 在任务回收后，自动产出“这次是否值得沉淀”的候选提案

产物：

1. `commander/transport/schemas/commander_improvement_candidate.schema.json`
2. `commander/transport/scripts/commander_propose_improvement.py`
3. `.runtime/commander/improvements/` 下的运行时候选文件

边界：

1. 只生成候选
2. 不自动写回文档
3. 不自动改 skill

完成判据：

1. 真实任务回收后，能得到结构化沉淀建议
2. 建议能明确分流到：文档 / 脚本 / skill

---

## 7. Phase 3：skill 候选升级链

目标：

- 把“重复问题 -> candidate skill patch”做成受控链路

产物：

1. skill 候选 patch 生成入口
2. skill 校验入口
3. 对应说明文档

边界：

1. 先生成 candidate
2. 校验通过后，仍由指挥官判断是否启用
3. 不允许直接改 live skill

完成判据：

1. 至少一类重复问题能生成 skill 候选
2. 候选通过校验后，才进入人工或指挥官决策

---

## 8. Phase 4：tool profile / 最小权限

目标：

- 让 packet 显式声明 worker 允许使用的最小工具集

产物：

1. packet schema 更新
2. dispatch / brief 更新
3. 回归测试

边界：

1. 只收紧执行边界
2. 不在本阶段引入复杂多 worker 编排

完成判据：

1. 至少一类真实任务能用受限工具集跑通
2. packet / brief / 回收链路都能看见当前工具边界

---

## 9. Phase 5：真实任务试跑与归档

目标：

- 用真实任务验证这条链不是只会修系统自己

产物：

1. 至少 2 次真实任务试跑记录
2. 时间线归档节点

完成判据：

1. 检索层、提案层或候选升级链至少有一条承载过真实任务
2. 指挥官回收成本确实下降

---

## 10. 停止条件

只有出现下面情况，才允许暂停默认继续：

1. 需要用户拍板
2. 出现真实技术阻塞
3. 当前 Phase 已整体收口，且不存在清楚的下一步最小动作

如果不满足这三条，默认继续推进下一个 Phase 或当前 Phase 的下一刀。

---

## 11. 当前执行口径

从本方案生效后，默认执行顺序是：

1. 先完成 `Phase 0`
2. 直接推进 `Phase 1`
3. `Phase 1` 验收通过后，再进入 `Phase 2`

当前不再把“继续不继续”留给聊天临时决定，而以本方案和任务卡为准。
