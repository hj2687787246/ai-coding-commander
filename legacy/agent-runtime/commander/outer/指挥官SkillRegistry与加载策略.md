# 指挥官 SkillRegistry 与加载策略

更新时间：2026-04-13

## 1. 文档定位

这份文档只保留一件事：说明 Phase C 里 `skill_source_registry` 的来源、优先级和加载方式。

它不是长历史回放，也不是 skill 升级方案本身。

## 2. `skill_source_registry` 的三个来源

`skill_source_registry` 只认三类来源：

1. `repo_skill_source`
   - 仓库内维护的 skill 真相源
   - 以 `commander/skill-source/` 为落点
2. `local_skills`
   - 当前机器本地已安装的 skill
   - 作为运行时可见来源，但不高于仓库真相源
3. `candidate_skills`
   - `.runtime/commander/skill_candidates/` 下的候选 skill
   - 只用于审查和对比，不作为 live skill 生效源

## 3. source 优先级

优先级固定为：

1. `repo truth-source`
2. `local installed`
3. `candidate`

含义很直接：

- 仓库里的真相源优先
- 本地安装副本其次
- 候选只做 review，不覆盖 live skill

## 4. 默认加载策略

默认是 `metadata-first`。

也就是说：

1. 先读 skill 的 metadata
2. 不默认注入 `SKILL.md` 全文
3. 只有 skill 命中后，才按需读取对应 `SKILL.md`

这样做的目的只有一个：先让 registry 决定“谁是哪个 skill、来自哪里、是否有效”，再决定要不要展开正文。

## 5. candidate 的边界

`candidate_skills` 是 review-only。

它可以被登记、被比较、被审查，但不能覆盖 live skill，也不能自动升级成生效源。

如果同名 skill 同时存在于 live source 和 candidate source，系统应当把 live source 视为有效源，candidate 仅保留为待审查条目。

## 6. 最小接班 / 排障读法

接班时只读三样：

1. `commander/outer/指挥官系统吸收DeepAgents落地清单.md` 的 Phase C 段
2. `commander/outer/指挥官skill候选升级说明.md`
3. 本文

排障时先看 registry 元数据，再决定是否展开 `SKILL.md`。

不要先回放长历史；先确认来源、优先级和当前是否命中即可。
