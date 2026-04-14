# 指挥官 warm worker 池说明

更新时间：2026-04-12

## 1. 文档定位

这份说明只解释一件事：
为什么当前指挥官体系要把“每次都新开一次性执行窗口”升级成“可预热、可复用、可回收”的 warm worker 池。

一句话说：

**常驻的是 worker profile 和外部状态，不是无限膨胀的隐式上下文。**

---

## 2. 当前 v1 目标

当前 warm worker 池 v1 只解决三件事：

1. 给执行编排层补一个 repo-native 的 worker registry
2. 让指挥官能 `acquire / reuse / release` worker slot
3. 把 worker 当前状态写进 `.runtime/commander/workers/`

当前 v1 不做：

1. 不做复杂多 worker 图编排
2. 不做平台级硬沙箱
3. 不做无限常驻上下文
4. 不做自动续派平台

---

## 3. 默认 worker profile

当前默认只固定两类：

1. `code-worker`
2. `verifier-worker`

含义是：

1. `code-worker`
   - 默认负责读代码、改代码、补测试、跑最小验证
2. `verifier-worker`
   - 默认负责更偏验证、回归、检查链和结果复核

---

## 4. 运行时结构

当前 worker 池运行时产物位于：

- `.runtime/commander/workers/registry.json`
- `.runtime/commander/workers/slots/<worker_id>.json`

其中：

1. `registry.json`
   - 当前 worker 总览
   - 各状态计数
   - 当前已有的 worker profile
2. `slots/<worker_id>.json`
   - 某个 worker 的当前状态快照

---

## 5. worker 状态

当前 v1 只保留四种状态：

1. `warm_idle`
   - worker 可复用，当前没有绑定任务
2. `busy`
   - worker 当前已被某个 task 占用
3. `completed_waiting_close`
   - 任务做完，但还没完成最终回收/关闭
4. `closed`
   - worker 生命周期结束，不再参与复用

一句话规则：

**默认尽量从 `warm_idle` 复用；任务做完后，不一定立刻关，而是先进入可见状态。**

---

## 6. 与 packet 的关系

当前 packet 会显式带上：

1. `worker_profile`
2. `preferred_worker_profile`
3. `reuse_allowed`
4. `tool_profile`
5. `allowed_tools`

含义是：

1. 这次任务默认由哪类 worker 承接
2. 是否优先尝试复用同 profile 的 warm worker
3. 即使复用 worker，也仍然以 packet / checkpoint 为真相源

---

## 7. 当前边界

当前 v1 是：

1. 一个可见的 worker registry
2. 一个可恢复的 worker slot 生命周期
3. 一个能承接“预热 + 复用”思路的最小实现

当前 v1 还不是：

1. LangGraph 式多 agent 平台
2. 平台原生 worker sandbox
3. 自动扩缩容系统

---

## 8. 当前推荐口径

从 v1 开始，默认执行口径是：

1. 指挥官先按 task packet 选择 `worker_profile`
2. 优先 acquire 一个匹配的 warm worker
3. worker 执行时仍按 packet / checkpoint / report 约束
4. 结果回收后，再决定释放成：
   - `warm_idle`
   - `completed_waiting_close`
   - `closed`

一句话收口：

**warm worker 池解决的是启动成本和角色稳定性，不是让 agent 无限制地保留上下文。**
