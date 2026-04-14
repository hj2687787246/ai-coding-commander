from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from commander.graph.adapters.worker_providers.base import (
    WorkerProviderDispatchContext,
    WorkerProviderCapabilities,
    WorkerProviderResult,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class LocalScriptWorkerProvider:
    provider_id = "local-script"
    capabilities = WorkerProviderCapabilities(
        read_files=True,
        edit_files=False,
        run_shell=True,
        run_tests=True,
        commit_git=False,
        review_only=False,
    )

    def dispatch(
        self,
        task_packet: dict[str, Any],
        *,
        dispatch_context: WorkerProviderDispatchContext | None = None,
    ) -> WorkerProviderResult:
        provider_input = task_packet.get("provider_input")
        if not isinstance(provider_input, dict):
            raise ValueError("local-script provider requires task_packet.provider_input")

        command = provider_input.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) and item.strip() for item in command
        ):
            raise ValueError(
                "local-script provider requires provider_input.command as a non-empty string list"
            )

        resolved_cwd = self._resolve_cwd(provider_input.get("cwd"))
        baseline_changed_files = self._repo_status_paths()
        completed = subprocess.run(
            command,
            cwd=resolved_cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        detected_changed_files = sorted(
            self._repo_status_paths() - baseline_changed_files
        )
        succeeded = completed.returncode == 0
        summary = self._summary(provider_input, succeeded=succeeded, task_packet=task_packet)
        recommended_next_step = self._recommended_next_step(
            provider_input, succeeded=succeeded
        )
        details = self._details(completed)
        changed_files = self._string_list(provider_input.get("changed_files"))
        for detected_path in detected_changed_files:
            if detected_path not in changed_files:
                changed_files.append(detected_path)
        report: dict[str, Any] = {
            "schema_version": "commander-harness-v1",
            "task_id": task_packet["task_id"],
            "status": "done" if succeeded else "blocked",
            "summary": summary,
            "changed_files": changed_files,
            "verification": [
                {
                    "name": "local-script",
                    "command": subprocess.list2cmdline(command),
                    "result": "passed" if succeeded else "failed",
                    "details": details,
                }
            ],
            "commit": {
                "message": (
                    provider_input.get("commit_message")
                    if isinstance(provider_input.get("commit_message"), str)
                    and provider_input.get("commit_message").strip()
                    else "local-script provider run"
                )
            },
            "risks": self._string_list(provider_input.get("risks")),
            "recommended_next_step": recommended_next_step,
            "needs_commander_decision": bool(
                provider_input.get("needs_commander_decision")
            )
            or not succeeded,
            "result_grade": "closed" if succeeded else "blocked",
            "next_action_owner": "commander",
            "continuation_mode": (
                "wait_user"
                if bool(provider_input.get("needs_user_decision"))
                else "close"
            ),
            "decision_reason": None,
            "split_suggestion": None,
            "needs_user_decision": bool(provider_input.get("needs_user_decision")),
            "user_decision_reason": (
                provider_input.get("user_decision_reason")
                if isinstance(provider_input.get("user_decision_reason"), str)
                else None
            ),
            "ready_for_user_delivery": bool(
                provider_input.get("ready_for_user_delivery")
            )
            and succeeded,
            "harness_metadata": {"is_dispatch_draft": False},
        }
        return WorkerProviderResult(
            status=report["status"],
            worker_report=report,
            evidence=[details],
            dispatch_metadata={"detected_changed_files": detected_changed_files},
        )

    def _resolve_cwd(self, cwd_value: Any) -> Path:
        if not isinstance(cwd_value, str) or not cwd_value.strip():
            return PROJECT_ROOT
        candidate = Path(cwd_value)
        resolved = (PROJECT_ROOT / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if resolved != PROJECT_ROOT and PROJECT_ROOT not in resolved.parents:
            raise ValueError("local-script provider cwd must stay within the repository")
        return resolved

    def _summary(
        self, provider_input: dict[str, Any], *, succeeded: bool, task_packet: dict[str, Any]
    ) -> str:
        key = "success_summary" if succeeded else "failure_summary"
        value = provider_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        task_id = task_packet.get("task_id")
        if succeeded:
            return f"Local script provider completed task {task_id}."
        return f"Local script provider failed task {task_id}."

    def _recommended_next_step(
        self, provider_input: dict[str, Any], *, succeeded: bool
    ) -> str:
        value = provider_input.get("recommended_next_step")
        if isinstance(value, str) and value.strip():
            return value.strip()
        if succeeded:
            return "Close the task after reviewing the local-script result."
        return "Review the local-script failure and decide whether to retry or split the task."

    def _details(self, completed: subprocess.CompletedProcess[str]) -> str:
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        parts = [f"exit_code={completed.returncode}"]
        if stdout:
            parts.append(f"stdout={stdout}")
        if stderr:
            parts.append(f"stderr={stderr}")
        return "\n".join(parts)

    def _repo_status_paths(self) -> set[str]:
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return set()
        paths: set[str] = set()
        for line in completed.stdout.splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            normalized = path.replace("\\", "/")
            if normalized:
                paths.add(normalized)
        return paths

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
