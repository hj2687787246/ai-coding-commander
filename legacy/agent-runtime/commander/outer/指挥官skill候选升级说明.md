# 指挥官 skill 候选升级说明

更新时间：2026-04-11

## 1. 文档定位

这份说明只解释一件事：

当学习循环判断“这次更适合沉淀成 skill”时，当前仓库怎样先生成 candidate，再校验，再决定要不要升级。

一句话说：

**先做候选，不直接改 live skill。**

---

## 2. 当前入口

生成候选：

```powershell
.\.venv\Scripts\python.exe scripts\commander_generate_skill_candidate.py --candidate <candidate.json>
```

校验候选：

```powershell
.\.venv\Scripts\python.exe scripts\commander_validate_skill_candidate.py --candidate-dir <candidate_dir>
```

---

## 3. 当前产物

当前会在：

```text
.runtime/commander/skill_candidates/<candidate_id>/
```

下生成：

1. `candidate_metadata.json`
2. `SKILL.candidate.md`

其中：

1. `candidate_metadata.json`
   - 保存结构化候选信息
2. `SKILL.candidate.md`
   - 保存给指挥官审查的 skill 草案

---

## 4. 当前边界

当前 v1 只做：

1. 从 `recommended_layer = skill` 的 candidate 生成 skill 候选
2. 校验候选结构是否完整
3. 为后续人工或指挥官批准做准备

当前 v1 不做：

1. 不覆盖 `C:\\Users\\26877\\.codex\\skills\\*` 下的 live skill
2. 不自动安装 skill
3. 不自动启用 skill
4. 不替代最终判断

所以它更像是：

**skill 升级链里的候选审查层，不是直接生效层。**
