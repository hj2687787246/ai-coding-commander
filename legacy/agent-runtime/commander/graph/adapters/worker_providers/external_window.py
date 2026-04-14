from __future__ import annotations

from typing import Any

from commander.graph.adapters.host_runtime import (
    HostRuntimeSessionContext,
    get_host_runtime_adapter,
)
from commander.graph.policies.launcher import resolve_launcher_preset
from commander.graph.adapters.worker_providers.base import (
    WorkerProviderCapabilities,
    WorkerProviderDispatchContext,
    WorkerProviderResult,
)


class ExternalWindowWorkerProvider:
    provider_id = "external-window"
    provider_label = "External Worker"
    host_adapter_id = "external-window"
    capabilities = WorkerProviderCapabilities(
        read_files=True,
        edit_files=True,
        run_shell=True,
        run_tests=True,
        commit_git=True,
        review_only=False,
    )

    def dispatch(
        self,
        task_packet: dict[str, Any],
        *,
        dispatch_context: WorkerProviderDispatchContext | None = None,
    ) -> WorkerProviderResult:
        if dispatch_context is None:
            raise ValueError(
                f"{self.provider_id} provider requires dispatch_context for external handoff"
            )

        provider_input = task_packet.get("provider_input")
        provider_notes: list[str] = []
        launcher_config: dict[str, Any] | None = None
        launcher_summary: dict[str, Any] | None = None
        if isinstance(provider_input, dict):
            raw_notes = provider_input.get("provider_notes")
            if isinstance(raw_notes, list):
                provider_notes = [
                    item.strip()
                    for item in raw_notes
                    if isinstance(item, str) and item.strip()
                ]
            try:
                launcher_config, launcher_summary = self._extract_launcher(provider_input)
            except ValueError as error:
                return WorkerProviderResult(
                    status="blocked",
                    worker_report=None,
                    evidence=[str(error)],
                    dispatch_metadata={
                        "mode": "external_window",
                        "provider_id": self.provider_id,
                        "provider_label": self.provider_label,
                        "host_adapter_id": self.host_adapter_id,
                        "task_id": dispatch_context.task_id,
                        "thread_id": dispatch_context.thread_id,
                        "launcher_error": str(error),
                    },
                )

        launch_prompt = self._build_launch_prompt(
            dispatch_context=dispatch_context,
            provider_notes=provider_notes,
        )
        launch_bundle_paths = self._build_launch_bundle_paths(dispatch_context)
        launch_bundle = self._build_launch_bundle(
            dispatch_context=dispatch_context,
            provider_notes=provider_notes,
            launch_prompt=launch_prompt,
            launch_bundle_paths=launch_bundle_paths,
            launcher_summary=launcher_summary,
        )
        host_adapter = get_host_runtime_adapter(self.host_adapter_id)
        host_session = host_adapter.create_or_attach_session(
            HostRuntimeSessionContext(
                thread_id=dispatch_context.thread_id,
                task_id=dispatch_context.task_id,
                runtime_root=dispatch_context.runtime_root,
                provider_id=self.provider_id,
                provider_label=self.provider_label,
                launch_prompt=launch_prompt,
                provider_notes=provider_notes,
                launch_bundle_paths=launch_bundle_paths,
                launch_bundle=launch_bundle,
                dispatch_idempotency_key=dispatch_context.dispatch_idempotency_key,
                worker_id=dispatch_context.worker_id,
                worker_profile=dispatch_context.worker_profile,
                preferred_worker_profile=dispatch_context.preferred_worker_profile,
                tool_profile=dispatch_context.tool_profile,
                allowed_tools=dispatch_context.allowed_tools,
                forbidden_paths=dispatch_context.forbidden_paths,
                owned_paths=dispatch_context.owned_paths,
                reuse_allowed=dispatch_context.reuse_allowed,
                dispatch_kind=dispatch_context.dispatch_kind,
                closure_policy=dispatch_context.closure_policy,
                governance=dispatch_context.governance,
                launcher_config=launcher_config,
            )
        )
        resolved_launch_bundle = (
            host_session.get("launch_bundle")
            if isinstance(host_session.get("launch_bundle"), dict)
            else launch_bundle
        )
        launch_status = str(resolved_launch_bundle.get("launch_status") or "").strip()
        provider_status = "blocked" if launch_status == "failed" else "waiting_worker"
        dispatch_metadata = {
            "mode": "external_window",
            "provider_id": self.provider_id,
            "provider_label": self.provider_label,
            "host_adapter_id": self.host_adapter_id,
            "task_id": dispatch_context.task_id,
            "thread_id": dispatch_context.thread_id,
            "packet_path": dispatch_context.packet_path,
            "context_bundle_path": dispatch_context.context_bundle_path,
            "worker_brief_path": dispatch_context.worker_brief_path,
            "worker_report_path": dispatch_context.worker_report_path,
            "resume_anchor_path": dispatch_context.resume_anchor_path,
            "checkpoint_path": dispatch_context.checkpoint_path,
            "status_path": dispatch_context.status_path,
            "launch_prompt": launch_prompt,
            "provider_notes": provider_notes,
            "launch_bundle_paths": launch_bundle_paths,
            "launch_bundle": resolved_launch_bundle,
            "host_session": self._host_session_summary(host_session),
        }
        evidence = [
            launch_prompt,
            f"host_session_id={host_session.get('session_id')}",
        ]
        launch_result = (
            resolved_launch_bundle.get("launch_result")
            if isinstance(resolved_launch_bundle.get("launch_result"), dict)
            else None
        )
        if provider_status == "blocked" and isinstance(launch_result, dict):
            error = launch_result.get("error")
            if isinstance(error, str) and error.strip():
                evidence.append(f"launch_error={error.strip()}")
        return WorkerProviderResult(
            status=provider_status,
            worker_report=None,
            evidence=evidence,
            dispatch_metadata=dispatch_metadata,
        )

    def _build_launch_prompt(
        self,
        *,
        dispatch_context: WorkerProviderDispatchContext,
        provider_notes: list[str],
    ) -> str:
        lines = [
            f"使用 {self.provider_label} 执行任务 {dispatch_context.task_id}。",
            f"runtime 路径：{dispatch_context.runtime_root}",
            "先按下面顺序读取，再严格按 packet 合同执行：",
            f"1. {dispatch_context.worker_brief_path}",
            f"2. {dispatch_context.packet_path}",
            f"3. {dispatch_context.context_bundle_path}",
            f"4. {dispatch_context.resume_anchor_path}",
            f"5. {dispatch_context.checkpoint_path}",
            "执行完成后，必须回填 machine-readable worker report：",
            f"- {dispatch_context.worker_report_path}",
            "读取 context_bundle.json 时，先看 read_policy / summary_lines / paths；只有当前切片真的需要更深背景时，再展开 deferred_paths。",
            "禁止跳过 packet 自由发挥；如果遇到阻塞或需要拆分，只能通过 worker_report 回到指挥官。",
        ]
        lines.extend(self._build_governance_prompt_lines(dispatch_context))
        if provider_notes:
            lines.append("额外说明：")
            lines.extend(f"- {item}" for item in provider_notes)
        return "\n".join(lines)

    def _build_launch_bundle_paths(
        self,
        dispatch_context: WorkerProviderDispatchContext,
    ) -> dict[str, str]:
        return {
            "packet_path": dispatch_context.packet_path,
            "context_bundle_path": dispatch_context.context_bundle_path,
            "worker_brief_path": dispatch_context.worker_brief_path,
            "worker_report_path": dispatch_context.worker_report_path,
            "resume_anchor_path": dispatch_context.resume_anchor_path,
            "checkpoint_path": dispatch_context.checkpoint_path,
            "status_path": dispatch_context.status_path,
        }

    def _build_launch_bundle(
        self,
        *,
        dispatch_context: WorkerProviderDispatchContext,
        provider_notes: list[str],
        launch_prompt: str,
        launch_bundle_paths: dict[str, str],
        launcher_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        read_order = [
            "worker_brief_path",
            "packet_path",
            "context_bundle_path",
            "resume_anchor_path",
            "checkpoint_path",
        ]
        if launcher_summary:
            launch_mode = "auto_launch"
            auto_launch_supported = True
            launch_status = "pending_launch"
            limitations = [
                "Auto launch is explicit opt-in and uses command-array execution only.",
                "A successful spawn does not guarantee the worker will produce a report.",
            ]
        else:
            launch_mode = "bundle_only"
            auto_launch_supported = False
            launch_status = "ready"
            limitations = [
                "This host does not safely auto-open a real Codex window.",
                "Use the launch bundle paths with an external window or manual handoff.",
            ]
        return {
            "schema_version": "commander-host-launch-bundle-v1",
            "provider_id": self.provider_id,
            "provider_label": self.provider_label,
            "host_adapter_id": self.host_adapter_id,
            "task_id": dispatch_context.task_id,
            "thread_id": dispatch_context.thread_id,
            "launch_mode": launch_mode,
            "auto_launch_supported": auto_launch_supported,
            "launch_status": launch_status,
            "launch_prompt": launch_prompt,
            "provider_notes": provider_notes,
            "read_order": read_order,
            "bundle_paths": launch_bundle_paths,
            "launcher": launcher_summary,
            "tool_profile": dispatch_context.tool_profile,
            "allowed_tools": list(dispatch_context.allowed_tools),
            "forbidden_paths": list(dispatch_context.forbidden_paths),
            "owned_paths": list(dispatch_context.owned_paths),
            "governance": dispatch_context.governance,
            "limitations": limitations,
        }

    def _build_governance_prompt_lines(
        self,
        dispatch_context: WorkerProviderDispatchContext,
    ) -> list[str]:
        governance = (
            dispatch_context.governance
            if isinstance(dispatch_context.governance, dict)
            else {}
        )
        tool_policy = (
            governance.get("tool_policy")
            if isinstance(governance.get("tool_policy"), dict)
            else {}
        )
        path_policy = (
            governance.get("path_policy")
            if isinstance(governance.get("path_policy"), dict)
            else {}
        )
        return [
            "执行治理合同：",
            f"- tool_profile: {dispatch_context.tool_profile or '(unspecified)'}",
            f"- allowed_tools: {self._format_sequence(dispatch_context.allowed_tools)}",
            f"- forbidden_paths: {self._format_sequence(dispatch_context.forbidden_paths)}",
            f"- owned_paths: {self._format_sequence(dispatch_context.owned_paths)}",
            f"- tool_policy.write_intent: {tool_policy.get('write_intent', '(unknown)')}",
            f"- tool_policy.read_only: {tool_policy.get('read_only', '(unknown)')}",
            f"- path_policy.protected_paths_declared: {path_policy.get('protected_paths_declared', '(unknown)')}",
            f"- path_policy.write_scope_declared: {path_policy.get('write_scope_declared', '(unknown)')}",
            "如 launch bundle / governance / packet 出现冲突，以 packet 为最终合同，但不得越过上述治理边界。",
        ]

    def _format_sequence(self, values: tuple[str, ...]) -> str:
        if not values:
            return "(none)"
        return ", ".join(values)

    def _host_session_summary(self, host_session: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": host_session.get("session_id"),
            "session_status": host_session.get("session_status"),
            "provider_id": host_session.get("provider_id"),
            "provider_label": host_session.get("provider_label"),
            "host_adapter_id": host_session.get("host_adapter_id"),
            "updated_at": host_session.get("updated_at"),
            "last_heartbeat_at": host_session.get("last_heartbeat_at"),
            "attached_report_path": host_session.get("attached_report_path"),
            "host_controls": host_session.get("host_controls"),
            "launch_bundle": host_session.get("launch_bundle"),
            "session_card": host_session.get("session_card"),
        }

    def _extract_launcher(
        self,
        provider_input: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        raw_launcher = provider_input.get("launcher")
        if not isinstance(raw_launcher, dict):
            return None, None
        preset_id = raw_launcher.get("preset_id")
        if isinstance(preset_id, str) and preset_id.strip():
            return resolve_launcher_preset(
                self.provider_id,
                preset_id.strip(),
                args=raw_launcher.get("args"),
                cwd=raw_launcher.get("cwd"),
                env=raw_launcher.get("env"),
                detached=raw_launcher.get("detached"),
            )
        command = raw_launcher.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) and item.strip() for item in command
        ):
            return None, None
        normalized_command = [item.strip() for item in command]
        launcher_config: dict[str, Any] = {
            "command": normalized_command,
            "detached": bool(raw_launcher.get("detached", True)),
        }
        summary: dict[str, Any] = {
            "command": normalized_command,
            "detached": launcher_config["detached"],
            "env_keys": [],
        }
        cwd = raw_launcher.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            launcher_config["cwd"] = cwd.strip()
            summary["cwd"] = cwd.strip()
        env = raw_launcher.get("env")
        if isinstance(env, dict):
            normalized_env: dict[str, str] = {}
            env_keys: list[str] = []
            for key, value in env.items():
                if (
                    isinstance(key, str)
                    and key.strip()
                    and isinstance(value, str)
                ):
                    normalized_key = key.strip()
                    normalized_env[normalized_key] = value
                    env_keys.append(normalized_key)
            if normalized_env:
                launcher_config["env"] = normalized_env
                summary["env_keys"] = sorted(env_keys)
        return launcher_config, summary
