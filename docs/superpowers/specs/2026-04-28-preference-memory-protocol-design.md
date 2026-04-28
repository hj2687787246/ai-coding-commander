# Preference Memory Protocol 设计

## 1. 背景

`commander-mode` 已经完成 High-Signal Commander v2 改造：它不再把 `.codex` 当作使用前提，而是把 `.codex` 作为自动记忆面和可选增强包。下一步要解决的是更细的一层问题：

**用户长期协作习惯不能只写成长文档，必须能被 skill 自动激活、检查和演化。**

在 `D:\Develop\Projects\Agent` 这类长任务仓库里，`AGENTS.md`、`.codex/AGENT.md` 和 `.codex/docs/协作偏好.md` 已经记录了很多规则。但“被读取”不等于“会执行”。如果偏好只是自然语言长文，模型在代码、测试、错误和新指令之间切换时仍然容易漏执行。

## 2. 目标

1. 把协作偏好从长说明书升级为结构化偏好卡。
2. 让 `commander-mode` 每轮自动选择本轮适用偏好，而不是机械灌入全部偏好。
3. 引入 Preference Gate：收尾前检查本轮是否遵守已激活偏好。
4. 支持候选偏好：用户纠正方向时先写候选，多次确认后升为稳定偏好。
5. 提供最小脚本，把偏好卡写回 `.codex/docs/协作偏好.md`。
6. 保持 Markdown 作为人类可读、可审查、可 git diff 的存储格式。

## 3. 非目标

1. 不引入数据库、向量库或常驻 memory service。
2. 不自动总结完整聊天历史。
3. 不把一次性任务选择写成长期偏好。
4. 不在 `D:\Develop\Projects\Agent` 里直接改业务代码或规则文件。
5. 不让偏好机制替代项目状态、验收记录或当前任务卡。

## 4. 记忆层分工

Preference Memory Protocol 使用三层结构：

1. Human Memory
   - Markdown 文件，主要是 `.codex/docs/协作偏好.md`。
   - 人可读、人可审、人可手动修正。
2. Structured Memory Cards
   - 每条偏好都有固定字段：`id/type/status/scope/triggers/rule/do/dont/evidence`。
   - 模型能按 trigger 激活，而不是读一整篇散文。
3. Activation And Gate
   - 每轮开始时选择 3-7 条相关偏好。
   - 每轮收尾前检查偏好执行情况。
   - 用户纠正方向时判断是否写入候选偏好。

## 5. 偏好卡格式

推荐在 Markdown 中使用二级分区和三级卡片标题：

```markdown
## Stable Preferences

### pref-token-roi

```yaml
type: preference
status: stable
scope: global
triggers:
  - planning
  - context_recovery
rule: token 使用目标是高价值，不是单纯低消耗。
do:
  - 读取能改变决策的真相源
  - 输出时压缩为结论、风险、下一步
dont:
  - 为保险机械读取所有模板
  - 把聊天过程写成长总结
evidence:
  - 2026-04-28 用户明确纠正：不是低 token，而是 token 花得有价值
```
```

候选偏好放到 `## Candidate Preferences` 下，格式相同但 `status: candidate`。

## 6. 激活规则

每次进入 commander mode 时：

1. 先判断用户意图：`orient / drive / implement / review / verify / handoff / architecture`。
2. 读取偏好卡索引或 `.codex/docs/协作偏好.md`。
3. 选择与当前意图和任务风险相关的 3-7 条偏好。
4. 内部执行这些偏好；对用户输出时只报告必要影响，不复述整份偏好。

示例：

- 用户说“继续”：激活恢复顺序、状态锁、每日时段、自动写回。
- 用户说“修这个”：激活 TDD、验证后下结论、不做补丁式兼容。
- 用户纠正方向：激活候选偏好写回和 Preference Gate。

## 7. Preference Gate

每轮收尾前，`commander-mode` 必须检查：

1. 本轮激活了哪些偏好。
2. 是否违反了任何已激活偏好。
3. 是否有新的长期偏好或候选偏好需要写回。
4. 是否有任务状态需要 checkpoint。
5. 是否有正式验收记录需要更新。

如果没有验证证据，不得用完成口径。

## 8. 写回规则

写入稳定偏好需要满足至少一个条件：

1. 用户明确说“我希望以后都...”。
2. 用户多次纠正同一协作方式。
3. 该偏好会改变未来 commander 行为。
4. 用户确认某候选偏好长期有效。

写入候选偏好适用于：

1. 用户刚刚纠正方向，但还不能确定长期稳定。
2. 偏好可能只适用于当前仓库。
3. 需要下次再观察是否重复出现。

不得写入：

1. 单次选项，例如“这次选 2”。
2. 临时任务范围。
3. 聊天原文。
4. 模型对用户偏好的猜测。

## 9. 脚本能力

新增 `sync_preference_memory.py`：

1. 默认目标：`.codex/docs/协作偏好.md`。
2. 支持 `stable` 和 `candidate` 两种状态。
3. 支持按 `id` upsert，避免重复卡片。
4. 使用纯标准库，不依赖 YAML parser。
5. 输出 JSON，便于 commander 写回后确认结果。

## 10. 验收标准

1. `SKILL.md` 明确包含 Preference Memory Protocol。
2. `SKILL.md` 明确每轮自动选择本轮适用偏好。
3. `SKILL.md` 明确 Preference Gate。
4. `SKILL.md` 明确用户纠正方向时应判断是否写入候选偏好。
5. `.codex` 模板里的 `协作偏好.md` 使用结构化偏好卡格式。
6. `sync_preference_memory.py` 有单元测试，覆盖 create、candidate/stable、upsert。
7. README 说明偏好记忆是 high-signal commander 的组成部分。

## 11. 一句话总结

Preference Memory Protocol 的目标，是让 commander 不只是读取用户偏好，而是能自动激活、检查、写回和演化用户偏好。
