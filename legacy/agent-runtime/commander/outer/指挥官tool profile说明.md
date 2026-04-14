# 指挥官 tool profile 说明

更新时间：2026-04-11

## 1. 文档定位

这份说明只解释一件事：

当前 packet / brief / status 怎样显式携带最小工具边界，让子执行 agent 的权限不再只存在于聊天描述里。

一句话说：

**先把工具边界写进合同，再谈更强的执行约束。**

---

## 2. 当前字段

当前 task packet 里新增了两个字段：

1. `tool_profile`
2. `allowed_tools`

含义是：

1. `tool_profile`
   - 这次任务使用什么边界档位
2. `allowed_tools`
   - 这次任务允许使用的最小工具集

---

## 3. 当前边界

当前 v1 只做：

1. packet 显式写出工具边界
2. worker brief 显式展示工具边界
3. status / checkpoint 保留当前工具边界

2026-04-14 补充：

1. 当 `commander_dispatch` 收到 `provider_id` 时，dispatch 会在写入 runtime 文件前执行 `validate_worker_dispatch_governance`
2. provider / tool_profile / allowed_tools / forbidden_paths / owned_paths 的不合法组合会直接拒绝 dispatch，不再只停留在 worker/provider 层提示
3. 未传 `provider_id` 的旧 transport 用法仍只做 schema 与合同写出，不假装拥有平台级沙箱隔离

当前 v1 不做：

1. 不做平台级沙箱硬拦截
2. 不做复杂权限系统
3. 不做按工具自动开关真实能力

所以它现在更像是：

**控制面可见的最小权限合同，而不是底层沙箱本身。**
