# Skill Trigger Matrix

更新时间：2026-05-07

This matrix records representative user wording that should route to a skill. It is a static regression aid, not a replacement for runtime skill loading.

Use it when:

- a skill did not trigger when expected;
- a skill description changes;
- commander routing changes;
- a new reusable workflow is added.

## Trigger Cases

| ID | User wording | Expected skill | Why |
| --- | --- | --- | --- |
| commander-continue | `继续，当前任务到哪了？` | `commander-mode` | Project state recovery and next safe action. |
| commander-handoff | `帮我把这个长任务交接给下一个窗口` | `commander-mode` | Handoff and recovery context. |
| commander-persistent-active | `我手动启用一次指挥官后，压缩和新窗口也要继续生效` | `commander-mode` | Persistent activation should write and recover `.codex/commander-active.json`. |
| reuse-sediment | `这个问题以后还会遇到，自动沉淀一下` | `commander-reuse-upgrader` | Repeated problem should be routed to reuse layer. |
| reuse-layer | `这个应该写进文档、脚本，还是做成 skill？` | `commander-reuse-upgrader` | Explicit markdown/script/skill decision. |
| reuse-agent-failure | `agent 又犯同一个错了，别再靠聊天记忆` | `commander-reuse-upgrader` | Repeated agent failure needs durable reuse. |
| skill-failure | `这个 skill 明明加载了但没有生效，debug 一下` | `identify-skill-failure` | Loaded skill failed to change behavior. |
| commander-skill-debug | `debug 当前指挥官 skill，看它有没有问题` | `identify-skill-failure` | Commander self-debug uses skill-document TDD; loaded violations use identify-skill-failure, while missed triggers use the Discovery Failure Gate. |
| skill-compress | `这个 SKILL.md 太长了，压缩但别丢门禁` | `compress-skill` | Skill is bloated and needs compression. |
| skill-modulize | `这个 skill 主文件太胖，把参考内容拆到 references` | `modulize-skill` | Main skill should route heavy references out. |
| skill-generalize | `我只是举个例子，不是只让你做这个，等等类似情况都要考虑` | `generalize` | Example wording should be generalized. |
| git-atomic | `帮我把这次改动拆成几个干净 commit` | `atomic-git-commits` | Commit history boundary and atomicity. |
| clarify-acceptance | `需求还没说清楚，先把验收标准问清楚` | `clarify-requirements` | Missing requirements and acceptance. |
| brainstorm-feature | `我要做个新功能，先一起想清楚方案` | `superpowers:brainstorming` | Creative feature design before implementation. |
| plan-multistep | `需求确认了，写一个多步骤实施计划` | `superpowers:writing-plans` | Spec exists and needs implementation plan. |
| tdd-feature | `实现这个功能，先按 TDD 来` | `superpowers:test-driven-development` | Feature implementation before production code. |
| debug-failure | `测试失败了，不要猜，系统调试一下` | `superpowers:systematic-debugging` | Bug or test failure investigation. |
| verify-complete | `你说修好了，先拿验证证据给我` | `superpowers:verification-before-completion` | Completion claim requires evidence. |
| execution-failure-repeat | `这个命令失败后已经找到正确写法了，下次同类操作别再先试错` | `execution-failure-guard` | Learned execution fixes should become the next attempt's default path before reuse-upgrader chooses durable storage. |
| execution-known-failure-preflight | `执行这个命令前先查一下 known-failures，别踩已知坑` | `execution-failure-guard` | Known-failure registry checks should happen before running a command that may match a known-bad method. |
| ps-utf8 | `PowerShell 读中文乱码，写文件要 UTF-8` | `ps-utf8-io` | Windows PowerShell UTF-8 I/O safety. |
| docx-edit | `帮我修改这个 Word 文档` | `docx` | Word document input or output. |
| pdf-extract | `读取这个 PDF 并提取表格` | `pdf` | PDF extraction. |
| pptx-update | `更新这个 PPTX 里的几页 slide` | `pptx` | PowerPoint input or output. |
| xlsx-clean | `清理这个 xlsx 表格并加公式` | `xlsx` | Spreadsheet manipulation. |
| webapp-test | `本地页面跑起来了，用浏览器测一下` | `webapp-testing` | Playwright/local web application verification. |
| frontend-layout | `这个 CSS 布局怎么调都不对，帮我定位` | `frontend-debugging` | CSS layout or DOM structure debugging. |
| ui-drift | `审计一下 UI 组件有没有重复和风格漂移` | `ui-style-consistency` | Design-system drift audit. |
| mysql-query | `连一下 MySQL 看看这张表` | `mysql-connect` | MySQL connectivity or query. |
| redis-inspect | `只读检查 Redis 里的 key` | `redis-read` | Redis read-only inspection. |
| mcp-build | `我要做一个 MCP server` | `mcp-builder` | MCP server implementation. |
| agent-runtime | `调试 agent tool-calling 循环和消息转换` | `developing-agents` | Agent runtime/tool-call behavior. |

## Review Rules

- Add a row when a real user wording fails to trigger the expected skill.
- Prefer the user's actual wording, especially Chinese synonyms.
- Do not add every installed skill by default; add cases for workflows that are likely to be missed.
- If the expected skill is unavailable, commander should state that and use the closest local method.
- If a broader skill shadows a narrower skill, decide whether to fix commander routing or the narrower skill description.
