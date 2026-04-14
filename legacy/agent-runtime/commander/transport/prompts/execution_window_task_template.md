# 执行窗口任务模板

优先把执行窗口提示压成“路径 + 合同”而不是长段任务重述。
如果当前任务已经由指挥官 harness 派发，默认只需要把下面路径替换为本轮 task 目录，然后要求执行窗口严格以 `packet.json` 为合同执行。

```text
主项目：
D:\Develop\Python-Project\Agent

先按 UTF-8 规则初始化 PowerShell，再开始读文件：
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
chcp 65001 > $null
$PSDefaultParameterValues['Get-Content:Encoding'] = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'utf8'

注意编码安全：凡是通过终端脚本写中文内容，不要直接把中文作为脚本字面量输出；优先用 Unicode 转义安全落盘。写完后必须做文件内容级校验，确认不是终端显示正常但文件实际写坏，也不是终端显示乱码但文件内容其实没问题。

你的角色：
你是执行窗口，负责在当前仓库内落地本轮任务，不重写指挥官体系，不把下阶段任务带进来。

先读取这几个产物，再按其中合同执行：
1. D:\Develop\Python-Project\Agent\.runtime\commander\tasks\<task_id>\worker_brief.md
2. D:\Develop\Python-Project\Agent\.runtime\commander\tasks\<task_id>\packet.json
3. D:\Develop\Python-Project\Agent\.runtime\commander\tasks\<task_id>\context_bundle.json
4. D:\Develop\Python-Project\Agent\.runtime\commander\tasks\<task_id>\resume_anchor.json
5. D:\Develop\Python-Project\Agent\.runtime\commander\tasks\<task_id>\checkpoint.json

`context_bundle.json` 默认按渐进式披露读取：
1. 先看 `read_policy`
2. 再看每个 entry 的 `summary_lines`
3. 先打开 entry 的 `paths`
4. 只有当 `packet.must_read`、当前验证、阻塞分析或当前切片真的需要更深背景时，再打开 `deferred_paths`

如果上下文压缩或中断，优先读 `resume_anchor.json`；也可以运行 `commander_resume.py --task-id <task_id>`，默认就会返回同样的 compact 锚点；如需显式说明，也可写成 `commander_resume.py --compact --task-id <task_id>`。只有需要更深状态时，再打开 `checkpoint.json`。

执行约束：
1. 以 packet 为任务合同，worker_brief 只做人读摘要
2. 不得触碰 packet 里的 forbidden_paths
3. 如遇阻塞、分叉、缺信息，只能回指挥官，不直接找用户做决策
4. 本轮完成后，除正常文字汇报外，再写一份 machine-readable report 到：
   D:\Develop\Python-Project\Agent\.runtime\commander\tasks\<task_id>\worker_report.json
5. 这份 report 必须符合：
   D:\Develop\Python-Project\Agent\commander\transport\schemas\commander_task_report.schema.json
6. report 至少包含：
   - task_id = <task_id>
   - status = done / blocked / need_split
   - summary
   - changed_files
   - verification
   - commit
   - risks
   - recommended_next_step
   - needs_commander_decision
   - result_grade
   - next_action_owner
   - continuation_mode
   - 如需要显式说明为什么继续/等待/拆分，再补 decision_reason
   - 如 status = need_split，优先补 split_suggestion
   - 如确实需要停给用户拍板，再补 needs_user_decision / user_decision_reason
   - 如结果已经可以直接回给用户，再补 ready_for_user_delivery = true

按 packet 执行时，默认做法是：
1. 先读 `context_bundle.read_policy` 和每个 entry 的 `summary_lines`
2. 优先打开 `packet.must_read` 和 entry 的 `paths`
3. 只有当前切片真的需要时，才展开 entry 的 `deferred_paths`
4. 只在 `packet.bounds` 内实施改动
5. 按 `packet.validation` 跑验证
6. 检查工作区，确认没有误伤 `packet.forbidden_paths`
7. 再输出文字汇报和 `worker_report.json`

必须遵守：
1. 用 apply_patch 改文件
2. 不要碰 `packet.forbidden_paths` 里的路径
3. 不要把真实密码、真实 DSN、私有 token 提交进 git
4. 改完后先跑 `packet.validation` 再汇报
5. 不要把准备做说成已经完成
6. 如果本轮有实际改动且验证通过，结束前要整理并提交 git；如果没有提交，必须明确说明为什么
7. commit message 必须使用中文
8. 如果通过终端脚本写中文内容，必须遵守上面的编码安全规则；不要直接把中文当脚本字面量输出
9. 写完 `worker_report.json` 后，必须做文件内容级校验，确认 JSON 字段和值没有因为终端编码写坏
10. 如果 `worker_report.json` 里有 `harness_metadata.is_dispatch_draft: true`，填写真实结果后必须把它改为 `false` 或删除该 metadata，再交给指挥官 ingest
11. `needs_user_decision` 只用于必须停给用户拍板的情况；内部卡点、拆任务或指挥官自决仍走 `needs_commander_decision`
12. `ready_for_user_delivery` 只用于“这轮结果已经可以由指挥官直接回给用户”，不要把普通子步骤完成也标成最终可交付
13. `result_grade / next_action_owner / continuation_mode` 要和真实治理语义对齐，不要只填旧字段
14. 如果判断应拆成后续任务，`status = need_split` 之外，再补 `split_suggestion.title / goal / reason`

汇报时必须按顺序写：
1. 结果状态是：已收口 / 部分完成 / 阻塞待决策
2. 实际改了什么
3. 为什么这么改
4. 跑了哪些验证，结果如何
5. 是否已提交 git；如果已提交，commit message 是什么；如果没有，原因是什么
6. 还有什么没做
7. 风险点是什么
8. 如果由你判断，下一步最合理的动作是什么
```

## 当前仓库推荐补充

如果当前任务还没接入 harness，才退回旧方式，把这些项补进“先读这些文件”或“至少验证”：

- `D:\Develop\Python-Project\Agent\docs\runbook.md`
- `D:\Develop\Python-Project\Agent\scripts\self_check.ps1`
- `D:\Develop\Python-Project\Agent\scripts\run_delivery_checks.py`

如果任务偏指挥官体系兼容，优先补：

- `D:\Develop\Python-Project\Agent\docs\指挥官任命.md`
- `D:\Develop\Python-Project\Agent\docs\新窗口启动指令模板.md`
- `D:\Develop\Python-Project\Agent\docs\指挥官当前任务卡.md`

如果任务偏“skill / 复用工具沉淀”，优先补：

- `D:\Develop\Python-Project\Agent\docs\复用问题沉淀与Skill升级协议.md`
- `D:\Develop\Python-Project\Agent\docs\指挥官问题索引.md`
- 在“必须遵守”或“这次只执行”里显式写清：
  - 先读 md 文档真相源，再决定落到文档 / 脚本 / skill
  - 不要跳过文档直接写 skill
  - 不复制 `plans / memory / reports / debt` 这类平行骨架
