# 执行窗口结果汇报模板

执行窗口完成后分两层交付：
1. 先按固定顺序写给指挥官看的文字汇报
2. 再落一份 machine-readable `worker_report.json`

目的是让指挥官窗口既能快速读人话，也能直接 ingest 结构化结果，而不是继续猜你做了什么。

如果当前任务由 harness dispatch 产出，优先直接编辑任务目录里已经预生成的 `worker_report.json` draft，而不是从零新建文件。
如果是从 checkpoint 恢复，文字汇报只需简短注明恢复自哪个 `checkpoint.json`，并让 `recommended_next_step` 和恢复动作对齐。
如果 draft 带有 `harness_metadata.is_dispatch_draft: true`，填写真实结果后必须把它改成 `false` 或按任务约定删除；否则 ingest 会继续把它当作 draft 拒绝。
如果这轮结果已经需要用户拍板，显式写 `needs_user_decision: true`，并补一条 `user_decision_reason`。
如果这轮结果已经可以直接回给用户作为最终结果，显式写 `ready_for_user_delivery: true`。

```text
1. 结果状态是：已收口 / 部分完成 / 阻塞待决策

2. 实际改了什么
- <改动 1>
- <改动 2>
- <如果有新增脚本或文档，写清路径>

3. 为什么这么改
- <理由 1>
- <理由 2>

4. 跑了哪些验证，结果如何
- <命令 1>：<通过 / 失败 / 部分通过>
- <命令 2>：<通过 / 失败 / 部分通过>
- <如果有未跑项，写清原因>

5. 是否已提交 git；如果已提交，commit message 是什么；如果没有，原因是什么
- <已提交 / 未提交>
- <commit message 或未提交原因>

6. 还有什么没做
- <未完成项 1>
- <未完成项 2>

7. 风险点是什么
- <风险 1>
- <风险 2>

8. 如果由你判断，下一步最合理的动作是什么
- <下一步建议>
```

## 本仓库补充要求

- 如果本轮是 harness 派工，文字里的“结果状态”建议和 report status 对齐：
  - 已收口 -> `done`
  - 部分完成 -> `need_split`
  - 阻塞待决策 -> `blocked`
- 如果动了文档，要说明新增入口是否和现有指挥官体系兼容
- 如果动了脚本，要说明默认路径跑了什么、可选路径跑了什么
- 如果工作区里本来就有未提交改动，要明确自己避开了哪些文件
- 如果提到“通过 UTF-8 正常读取”，最好说明你实际做了文件内容级校验

## worker_report.json 最小骨架

把下面骨架按本轮实际内容填写，并确保符合 `commander/transport/schemas/commander_task_report.schema.json`：

```json
{
  "task_id": "<task_id>",
  "status": "done",
  "summary": "<一句话总结本轮结果>",
  "changed_files": [
    "commander/transport/prompts/execution_window_task_template.md",
    "commander/transport/prompts/execution_window_report_template.md"
  ],
  "verification": [
    {
      "name": "pytest",
      "command": ".\\.venv\\Scripts\\python.exe -m pytest -q tests/test_commander_harness.py",
      "result": "passed",
      "details": "<可选，补充关键结果>"
    },
    {
      "name": "git diff --check",
      "command": "git diff --check",
      "result": "passed"
    }
  ],
  "commit": {
    "hash": "<可选，已提交再填>",
    "message": "<已提交则填中文 commit message；未提交也要给原因>"
  },
  "risks": [
    "<风险 1>"
  ],
  "recommended_next_step": "<建议指挥官下一步动作>",
  "needs_commander_decision": false,
  "result_grade": "closed",
  "next_action_owner": "commander",
  "continuation_mode": "close",
  "decision_reason": null,
  "split_suggestion": null,
  "needs_user_decision": false,
  "user_decision_reason": null,
  "ready_for_user_delivery": false,
  "harness_metadata": {
    "is_dispatch_draft": false
  }
}
```

补充约定：

- `status` 只能是 `done`、`blocked`、`need_split`
- `result_grade` 只能是 `closed`、`partial`、`blocked`
- `next_action_owner` 只能是 `commander`、`user`、`worker`
- `continuation_mode` 只能是 `close`、`followup`、`split`、`wait_user`
- `verification[].result` 只能是 `passed`、`failed`、`skipped`
- `commit` 可以为 `null`，但只在确实未提交且你要明确说明原因时使用
- 如果 dispatch 已预生成 `worker_report.json`，默认在原文件上改，不要另起一个平行 report 文件
- 如果 draft 带有 `harness_metadata.is_dispatch_draft: true`，完成填写后要把它改成 `false` 或删除该 metadata，再交给指挥官 ingest
- `needs_user_decision: true` 只用于“确实必须停给用户拍板”的情况，不要拿它代替 `needs_commander_decision`
- `ready_for_user_delivery: true` 只用于“这轮结果已经可以由指挥官直接回给用户”的情况
- `decision_reason` 用来显式说明当前 decision gate 的原因；如果是 `need_split`，优先同时补 `split_suggestion`
