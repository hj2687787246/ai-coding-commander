from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import commander.graph.adapters.worker_providers.external_window as external_window_module
from commander.graph.adapters.worker_providers import (
    TOOL_PROFILES,
    WorkerDispatchGovernanceError,
    get_worker_provider,
    list_worker_provider_metadata,
    validate_worker_dispatch_governance,
)
from commander.graph.adapters.worker_providers.base import WorkerProviderDispatchContext
from commander.graph.policies.lane_contract import is_read_only_worker_profile
from commander.graph.policies.launcher import resolve_launcher_preset
from commander.transport.scripts.commander_dispatch import build_packet, dispatch_task


def make_packet(
    *,
    task_id: str = "provider-governance-task",
    worker_profile: str = "code-worker",
    tool_profile: str = "control_plane_safe_write",
    allowed_tools: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    owned_paths: list[str] | None = None,
    dispatch_kind: str = "fresh",
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "worker_profile": worker_profile,
        "tool_profile": tool_profile,
        "allowed_tools": allowed_tools or ["shell_command", "apply_patch"],
        "forbidden_paths": forbidden_paths or ["config/rag.yml"],
        "owned_paths": owned_paths or [],
        "dispatch_kind": dispatch_kind,
        "closure_policy": "close_when_validated",
    }


def test_worker_provider_registry_exposes_metadata() -> None:
    providers = {item.provider_id: item for item in list_worker_provider_metadata()}

    assert "codex" in providers
    assert "local-script" in providers
    assert providers["codex"].default_tool_profile == "control_plane_safe_write"
    assert providers["codex"].supported_launcher_presets == ("codex-cli",)
    assert providers["qwen"].capabilities.review_only is True
    assert is_read_only_worker_profile("analysis-worker") is True
    assert providers["codex"].supported_tool_profiles
    assert "commander_readonly" in providers["codex"].supported_tool_profiles
    assert "commander_docs_write" in providers["codex"].supported_tool_profiles
    assert TOOL_PROFILES["control_plane_safe_write"].allowed_tools == (
        "shell_command",
        "apply_patch",
    )
    assert TOOL_PROFILES["commander_docs_write"].read_only is False
    assert TOOL_PROFILES["commander_readonly"].read_only is True


def test_get_worker_provider_attaches_registry_metadata() -> None:
    provider = get_worker_provider("codex")

    assert provider.provider_id == "codex"
    assert provider.metadata.provider_id == "codex"
    assert provider.metadata.host_adapter_id == "external-window"


def test_resolve_launcher_preset_uses_provider_supported_contract() -> None:
    config, summary = resolve_launcher_preset(
        "codex",
        "codex-cli",
        args=["exec", "--json"],
        cwd=".",
        env={"CODEX_HOME": "D:/Codex"},
        detached=False,
    )

    assert config["command"] == ["codex", "exec", "--json"]
    assert config["cwd"] == "."
    assert config["env"] == {"CODEX_HOME": "D:/Codex"}
    assert config["detached"] is False
    assert summary["preset_id"] == "codex-cli"
    assert summary["env_keys"] == ["CODEX_HOME"]


def test_resolve_launcher_preset_rejects_unsupported_provider_preset() -> None:
    with pytest.raises(ValueError):
        resolve_launcher_preset("codex", "claude-code-cli")


def test_external_window_provider_blocks_on_invalid_launcher_preset() -> None:
    provider = get_worker_provider("codex")
    result = provider.dispatch(
        {
            "task_id": "launcher-invalid-task",
            "provider_input": {"launcher": {"preset_id": "claude-code-cli"}},
        },
        dispatch_context=WorkerProviderDispatchContext(
            thread_id="thread-launcher-invalid",
            task_id="launcher-invalid-task",
            runtime_root="D:/runtime",
            packet_path="packet.json",
            context_bundle_path="context.json",
            worker_brief_path="brief.md",
            worker_report_path="worker_report.json",
            resume_anchor_path="resume.json",
            checkpoint_path="checkpoint.json",
            status_path="status.json",
        ),
    )

    assert result.status == "blocked"
    assert "does not support launcher preset" in result.dispatch_metadata["launcher_error"]


def test_external_window_provider_resolves_valid_launcher_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = get_worker_provider("codex")
    captured_context: dict[str, object] = {}

    class FakeAdapter:
        def create_or_attach_session(self, session_context):
            captured_context["launcher_config"] = session_context.launcher_config
            captured_context["launch_bundle"] = session_context.launch_bundle
            return {
                "session_id": "host-test",
                "session_status": "waiting_worker",
                "provider_id": "codex",
                "provider_label": "Codex Worker Window",
                "host_adapter_id": "external-window",
                "updated_at": "2026-04-13T00:00:00Z",
                "last_heartbeat_at": None,
                "attached_report_path": None,
                "host_controls": {},
                "launch_bundle": session_context.launch_bundle,
                "session_card": {"launch_status": "pending_launch"},
            }

    monkeypatch.setattr(
        external_window_module,
        "get_host_runtime_adapter",
        lambda _adapter_id: FakeAdapter(),
    )
    result = provider.dispatch(
        {
            "task_id": "launcher-valid-task",
            "provider_input": {
                "launcher": {
                    "preset_id": "codex-cli",
                    "args": ["exec", "--json"],
                    "cwd": ".",
                    "env": {"CODEX_HOME": "D:/Codex"},
                    "detached": False,
                }
            },
        },
        dispatch_context=WorkerProviderDispatchContext(
            thread_id="thread-launcher-valid",
            task_id="launcher-valid-task",
            runtime_root="D:/runtime",
            packet_path="packet.json",
            context_bundle_path="context.json",
            worker_brief_path="brief.md",
            worker_report_path="worker_report.json",
            resume_anchor_path="resume.json",
            checkpoint_path="checkpoint.json",
            status_path="status.json",
        ),
    )

    launcher_config = captured_context["launcher_config"]
    launch_bundle = captured_context["launch_bundle"]

    assert result.status == "waiting_worker"
    assert launcher_config["command"] == ["codex", "exec", "--json"]
    assert launcher_config["env"] == {"CODEX_HOME": "D:/Codex"}
    assert launcher_config["detached"] is False
    assert launch_bundle["launcher"]["preset_id"] == "codex-cli"
    assert launch_bundle["launcher"]["command"] == ["codex", "exec", "--json"]


def test_validate_worker_dispatch_governance_accepts_code_capable_provider() -> None:
    governance = validate_worker_dispatch_governance(
        make_packet(),
        provider_id="codex",
    )

    assert governance.ok is True
    assert governance.provider.provider_id == "codex"
    assert governance.tool_profile.profile_id == "control_plane_safe_write"
    assert governance.allowed_tools == ("shell_command", "apply_patch")
    assert governance.forbidden_paths == ("config/rag.yml",)
    assert governance.owned_paths == ()
    assert governance.tool_policy["write_intent"] is True
    assert governance.tool_policy["requested_tools"] == ["shell_command", "apply_patch"]
    assert governance.path_policy["write_scope_declared"] is False
    assert any("owned_paths" in item for item in governance.contract_notes)


def test_validate_worker_dispatch_governance_accepts_explicit_read_only_profile() -> None:
    governance = validate_worker_dispatch_governance(
        make_packet(
            worker_profile="analysis-worker",
            tool_profile="commander_readonly",
            allowed_tools=["shell_command"],
        ),
        provider_id="codex",
    )

    assert governance.ok is True
    assert governance.tool_profile.profile_id == "commander_readonly"
    assert governance.tool_profile.read_only is True
    assert governance.tool_policy["write_intent"] is False
    assert governance.path_policy["write_scope_declared"] is False


def test_validate_worker_dispatch_governance_accepts_scribe_docs_surface_write() -> None:
    governance = validate_worker_dispatch_governance(
        make_packet(
            worker_profile="scribe-worker",
            tool_profile="commander_docs_write",
            allowed_tools=["shell_command", "apply_patch"],
            owned_paths=[
                "AGENTS.md",
                "commander/core/主文档.md",
                "commander/state/当前任务卡.md",
                "commander/outer/agent_workbench.md",
                "commander/skill-source/commander-mode/SKILL.md",
            ],
        ),
        provider_id="codex",
    )

    assert governance.ok is True
    assert governance.tool_profile.profile_id == "commander_docs_write"
    assert governance.tool_profile.read_only is False
    assert governance.owned_paths == (
        "AGENTS.md",
        "commander/core/主文档.md",
        "commander/state/当前任务卡.md",
        "commander/outer/agent_workbench.md",
        "commander/skill-source/commander-mode/SKILL.md",
    )
    assert governance.path_policy["write_scope_declared"] is True
    assert governance.tool_policy["write_intent"] is True


def test_validate_worker_dispatch_governance_rejects_scribe_with_wrong_tool_profile() -> None:
    with pytest.raises(WorkerDispatchGovernanceError) as error:
        validate_worker_dispatch_governance(
            make_packet(
                worker_profile="scribe-worker",
                tool_profile="control_plane_safe_write",
                allowed_tools=["shell_command", "apply_patch"],
                owned_paths=["commander/core/主文档.md"],
            ),
            provider_id="codex",
        )

    assert error.value.provider_id == "codex"
    assert any("scribe worker_profile" in item for item in error.value.violations)


def test_validate_worker_dispatch_governance_rejects_scribe_non_docs_owned_paths() -> None:
    with pytest.raises(WorkerDispatchGovernanceError) as error:
        validate_worker_dispatch_governance(
            make_packet(
                worker_profile="scribe-worker",
                tool_profile="commander_docs_write",
                allowed_tools=["shell_command", "apply_patch"],
                owned_paths=["commander/graph/graph.py"],
            ),
            provider_id="codex",
        )

    assert error.value.provider_id == "codex"
    assert any("escape commander docs surfaces" in item for item in error.value.violations)


def test_validate_worker_dispatch_governance_rejects_read_only_lane_with_writable_profile() -> None:
    with pytest.raises(WorkerDispatchGovernanceError) as error:
        validate_worker_dispatch_governance(
            make_packet(
                worker_profile="analysis-worker",
                tool_profile="control_plane_safe_write",
            ),
            provider_id="codex",
        )

    assert error.value.provider_id == "codex"
    assert any("read-only worker_profile" in item for item in error.value.violations)


def test_validate_worker_dispatch_governance_rejects_review_only_provider_for_write_task() -> None:
    with pytest.raises(WorkerDispatchGovernanceError) as error:
        validate_worker_dispatch_governance(
            make_packet(),
            provider_id="qwen",
        )

    assert error.value.provider_id == "qwen"
    assert any("review-only provider" in item for item in error.value.violations)
    assert error.value.governance["tool_profile"]["profile_id"] == "control_plane_safe_write"


def test_dispatch_task_rejects_provider_governance_failure() -> None:
    runtime_root = Path("codex_test/__dispatch_governance_preflight_sentinel__")
    packet = {
        **make_packet(),
        "title": "Governance preflight",
        "goal": "Reject an unsafe provider before dispatch writes runtime files",
        "must_read": ["README.md"],
        "bounds": ["Do not write runtime files when governance fails"],
        "validation": ["pytest"],
        "reuse_allowed": False,
        "source_task_id": None,
        "parent_task_id": None,
        "task_owner": "commander",
        "report_contract": {
            "allowed_statuses": ["done", "blocked", "need_split"],
            "required_fields": ["task_id", "status", "summary"],
        },
        "status": "dispatched",
    }

    with pytest.raises(WorkerDispatchGovernanceError) as error:
        dispatch_task(runtime_root, packet, provider_id="qwen")

    assert error.value.provider_id == "qwen"
    assert any("review-only provider" in item for item in error.value.violations)
    assert not (runtime_root / "tasks" / "provider-governance-task").exists()


def test_build_packet_defaults_read_only_lane_to_commander_readonly() -> None:
    packet = build_packet(
        argparse.Namespace(
            runtime_root=None,
            task_id="packet-readonly-task",
            title="Read only lane",
            goal="Exercise packet default mapping",
            must_read=[],
            bound=[],
            validation=[],
            forbidden_path=[],
            owned_path=[],
            worker_profile="analysis-worker",
            preferred_worker_profile=None,
            tool_profile="default",
            allowed_tool=[],
            no_reuse=False,
            dispatch_kind="fresh",
            source_task_id=None,
            parent_task_id=None,
            task_owner="commander",
            closure_policy="close_when_validated",
            note=[],
            context_tag=[],
            spec_ref=[],
            provider_id=None,
            idempotency_key=None,
        )
    )

    assert packet["tool_profile"] == "commander_readonly"


def test_build_packet_defaults_scribe_lane_to_commander_docs_write() -> None:
    packet = build_packet(
        argparse.Namespace(
            runtime_root=None,
            task_id="packet-scribe-task",
            title="Docs write lane",
            goal="Exercise packet default mapping for scribe lane",
            must_read=[],
            bound=[],
            validation=[],
            forbidden_path=[],
            owned_path=[],
            worker_profile="scribe-worker",
            preferred_worker_profile=None,
            tool_profile="default",
            allowed_tool=[],
            no_reuse=False,
            dispatch_kind="fresh",
            source_task_id=None,
            parent_task_id=None,
            task_owner="commander",
            closure_policy="close_when_validated",
            note=[],
            context_tag=[],
            spec_ref=[],
            provider_id=None,
            idempotency_key=None,
        )
    )

    assert packet["tool_profile"] == "commander_docs_write"
    assert packet["allowed_tools"] == ["shell_command", "apply_patch"]


def test_validate_worker_dispatch_governance_rejects_unknown_tool_inside_profile() -> None:
    with pytest.raises(WorkerDispatchGovernanceError) as error:
        validate_worker_dispatch_governance(
            make_packet(allowed_tools=["shell_command", "magic_tool"]),
            provider_id="codex",
        )

    assert any("exceed tool_profile" in item for item in error.value.violations)


def test_validate_worker_dispatch_governance_rejects_unsupported_dispatch_kind() -> None:
    with pytest.raises(WorkerDispatchGovernanceError) as error:
        validate_worker_dispatch_governance(
            make_packet(
                tool_profile="review_only",
                allowed_tools=["shell_command"],
                dispatch_kind="split",
            ),
            provider_id="qwen",
        )

    assert any("does not support dispatch_kind" in item for item in error.value.violations)


def test_validate_worker_dispatch_governance_rejects_owned_path_forbidden_overlap() -> None:
    with pytest.raises(WorkerDispatchGovernanceError) as error:
        validate_worker_dispatch_governance(
            make_packet(
                forbidden_paths=["commander/graph"],
                owned_paths=["commander/graph/nodes"],
            ),
            provider_id="codex",
        )

    assert any("overlaps forbidden_path" in item for item in error.value.violations)
    assert error.value.governance["owned_paths"] == ["commander/graph/nodes"]
    assert error.value.governance["path_policy"]["conflicting_path_pairs"] == [
        {
            "owned_path": "commander/graph/nodes",
            "forbidden_path": "commander/graph",
        }
    ]
