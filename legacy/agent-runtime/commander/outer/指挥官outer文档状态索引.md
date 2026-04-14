# 指挥官 outer 文档状态索引

更新时间：2026-04-14

## 1. 文档定位

这份索引用来回答一个问题：

**`commander/outer` 里的文档哪些已经完成，哪些只是长期参考，哪些还带后续增强。**

判断当前是否还有任务，不看 `outer` 文档里的“下一步 / 后续 / backlog”字样，而是优先看：

1. `commander_task_catalog --summary`
2. `commander_stop_gate`
3. `commander/state/当前任务卡.md`
4. `commander/state/时间线.md`

截至 2026-04-14 的快照结论：

- 当前没有 active 任务。
- DeepAgents 吸收链已完成并归档。
- `outer` 目录不是待办清单，而是方案库、模板库、交接材料库和历史设计记录。

---

## 2. 状态标签

- `已落地`：对应主线已经实现、验证并写入时间线；文档保留为事实记录或策略说明。
- `长期参考`：不是“完成/未完成”型文档，而是工作规则、模板或交接入口。
- `混合方案`：主体已经落地，但文档内保留后续增强方向；这些增强不等于当前 active 任务。
- `历史方案`：已被后续实现吸收，保留用于追溯为什么这么做。

---

## 3. 当前文档状态

| 文档 | 当前状态 | 怎么理解 |
| --- | --- | --- |
| `agent_workbench.md` | 长期参考 | 执行窗口工作台说明，不是待办清单。 |
| `新窗口交接说明.md` | 长期参考 | 新窗口接班入口，不按完成度管理。 |
| `新窗口启动指令模板.md` | 长期参考 | 执行窗口提示词模板，按需维护。 |
| `指挥官harness-v1实施优先级.md` | 历史方案 | harness v1 早期优先级记录，主体能力已被后续 runtime 吸收。 |
| `指挥官Hermes-lite受控进化方案.md` | 历史方案 | Hermes-lite 吸收口径记录，后续不作为当前 active 主线。 |
| `指挥官LangGraph运行时项目化方案.md` | 混合方案 | Agent 仓库的 LangGraph/runtime 适配实验记录；已落地部分很多，但不再代表通用指挥官 skill 的本体方向。 |
| `指挥官SkillRegistry与加载策略.md` | 已落地 | Skill Registry / Source Precedence 的 Phase C 策略文档。 |
| `指挥官skill候选升级说明.md` | 已落地 | skill candidate 审批与升级说明，作为规则参考。 |
| `指挥官tool profile说明.md` | 已落地 | tool profile 规则说明，作为治理参考。 |
| `指挥官瘦身审计清单.md` | 长期参考 | 区分 AI coding harness 核心、实验适配层和未来删除候选。 |
| `指挥官warm worker池说明.md` | 历史方案 | warm worker / worker pool 设计说明，主体能力已进入后续 runtime 治理。 |
| `指挥官调度与结果回收harness-v1.md` | 已落地 | 调度、report、active_subagents、回收规则说明。 |
| `指挥官调度原则.md` | 长期参考 | 指挥官调度原则，不是待办清单。 |
| `指挥官多Worker并行与会话复用方案.md` | 混合方案 | 多 worker 并行和会话复用基线已落地；更强 detached session pool 属于后续增强。 |
| `指挥官记忆检索说明.md` | 已落地 | 记忆检索入口说明，作为使用文档。 |
| `指挥官接班验收清单.md` | 长期参考 | 接班验收 checklist，不按完成度管理。 |
| `指挥官六层Harness与Hermes融合落地方案.md` | 历史方案 | 六层 harness / Hermes 融合方案，主体已被 5.5 后续治理吸收。 |
| `指挥官系统完善方案.md` | 已落地 | 5.5 指挥官系统完善工程已完成集中治理，后续按维护入口增量运行。 |
| `指挥官系统吸收DeepAgents落地清单.md` | 已落地 | DeepAgents Phase A-D 已完成并归档。 |
| `指挥官学习循环提案说明.md` | 已落地 | 学习循环 / candidate 提案说明，作为规则参考。 |

---

## 4. 已完成主线

当前按任务真相源已完成并归档的 `outer` 相关主线：

- `5.5 指挥官系统完善工程`
- `5.6 LangGraph 指挥官运行时项目化`
- `5.7 多 Worker 并行调度与会话复用工程`
- `6.0 DeepAgents Phase A / Compact Resume Ledger`
- `6.1 DeepAgents Phase B / Tool / Path Governance Middleware`
- `6.2 DeepAgents Phase C / Skill Registry 与 Source Precedence`
- `6.3 DeepAgents Phase D / Better-Harness 风格离线实验场`
- `6.4 Host Runtime Integration / external_window 自动拉起第一刀`

---

## 5. 不应误判成当前任务的后续增强

下面这些内容可能还会出现在历史方案文档里，但当前不是 active 任务：

- 更强的 detached session pool。
- released reusable session 自动接收新 task。
- 更高层聊天入口的端到端短确认词绑定。
- 更完整的可见演示入口或 UI 化状态面板。
- 外部定时调度、archive compaction 等更重维护机制。
- 把 LangGraph / host runtime / worker pool 推广成所有仓库都必须安装的通用框架。

如果以后要做其中某一项，应作为新任务重新写入 `当前任务卡.md`，不要因为 `outer` 历史方案里出现“后续 / 下一步”就自动当成当前未完成任务。

---

## 6. 快速判断规则

如果以后又不清楚“到底完成没有”，按这个顺序判断：

1. `commander_task_catalog --summary` 里 `active_like_task_count` 是否为 `0`。
2. `commander_stop_gate` 是否返回 `stop_allowed=true`。
3. `当前任务卡.md` 是否明确写着无活跃任务。
4. `时间线.md` 是否有对应完成事实。
5. 最后再看 `outer` 文档的方案细节。

`outer` 文档里的 backlog 只能说明“将来可以增强”，不能单独证明“当前任务没完成”。
