# Spec Artifacts

`commander/specs/` 存放 repo-native 的 Spec-Kit / SDD 合同，不是聊天摘要，也不是另起一套 `plans/` 平行骨架。

## 约定

1. 每个 spec artifact 都必须通过 `commander/transport/schemas/commander_spec_artifact.schema.json`。
2. spec 文件优先落在 `commander/specs/<spec_id>.json`。
3. `objective plan / phase plan / goal queue` 通过 `spec_refs` 挂载 spec artifact。
4. `dispatch` 会把 `spec_refs` 送进 `packet.json`、`worker_brief.md` 和 `context_bundle.json`。
5. `context_bundle.json` 只引用 repo-native 事实源，不复制 `plans / memory / reports / debt` 这套并行骨架。

## 推荐入口

生成草稿：

```powershell
.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_spec_kit template --spec-id task-5-7-spec-template --title "Spec-Kit / SDD artifact layer"
```

校验文件：

```powershell
.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_spec_kit validate --spec-file commander/specs/task-5-7-spec-template.json
```

生成可挂载的 ref：

```powershell
.\.venv\Scripts\python.exe -m commander.transport.scripts.commander_spec_kit ref --spec-file commander/specs/task-5-7-spec-template.json
```

## 字段层次

- `constitution`: 原则、边界、护栏
- `specification`: 需求、接口、约束
- `planning`: milestone 与推进顺序
- `tasking`: dispatch 规则、任务契约、packet 约束
- `implementation_state`: 当前阶段、证据、阻塞
- `acceptance` / `non_goals` / `invariants` / `truth_sources`: 用来收口而不是再开口
