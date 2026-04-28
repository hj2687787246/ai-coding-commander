# Preference Memory Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured preference memory cards, activation rules, Preference Gate guidance, and a script for writing preference cards.

**Architecture:** Keep Markdown as the human-readable memory store, add a small standard-library script for upserting structured preference cards, and lock the behavior with tests. Update `commander-mode` so it activates relevant preferences each turn and checks them before completion.

**Tech Stack:** Markdown docs, Python 3 standard library, pytest.

---

## File Structure

### New Files

- `skills/commander-mode/scripts/sync_preference_memory.py`
  - Upserts structured preference cards into `.codex/docs/协作偏好.md`.
- `tests/test_sync_preference_memory.py`
  - Tests create, stable/candidate routing, and idempotent upsert behavior.

### Modified Files

- `skills/commander-mode/SKILL.md`
  - Adds Preference Memory Protocol, preference activation, and Preference Gate.
- `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/协作偏好.md`
  - Replaces generic placeholder with structured preference card sections.
- `README.md`
  - Describes Preference Memory Protocol as part of high-signal commander.
- `tests/test_high_signal_commander_docs.py`
  - Adds documentation contract tests for preference memory.
- `.codex/docs/当前任务.md`
  - Records implementation checkpoint.

---

### Task 1: Lock Preference Memory Contract

**Files:**
- Modify: `tests/test_high_signal_commander_docs.py`

- [x] Add tests asserting `SKILL.md` contains `Preference Memory Protocol`, `Preference Gate`, `本轮适用偏好`, `候选偏好`, and `用户纠正方向`.
- [x] Add tests asserting template `协作偏好.md` contains `Stable Preferences`, `Candidate Preferences`, `type: preference`, `triggers:`, `do:`, `dont:`, and `evidence:`.
- [x] Run `python -m pytest tests/test_high_signal_commander_docs.py -q` and confirm the new tests fail before implementation.

---

### Task 2: Add Preference Memory Sync Script

**Files:**
- Create: `skills/commander-mode/scripts/sync_preference_memory.py`
- Create: `tests/test_sync_preference_memory.py`

- [x] Write failing tests for creating a missing preference file, adding a stable card, adding a candidate card, and replacing an existing card with the same id.
- [x] Implement a standard-library script with `sync_preference_memory(repo_root, memory_id, status, scope, triggers, rule, do_items, dont_items, evidence_items)`.
- [x] Add CLI flags: `--repo`, `--id`, `--status`, `--scope`, repeated `--trigger`, `--rule`, repeated `--do`, repeated `--dont`, repeated `--evidence`.
- [x] Run `python -m pytest tests/test_sync_preference_memory.py -q` and confirm the tests pass.

---

### Task 3: Update Preference Template And Commander Skill

**Files:**
- Modify: `skills/commander-mode/references/templates/project-codex-standard/.codex/docs/协作偏好.md`
- Modify: `skills/commander-mode/SKILL.md`

- [x] Replace the template preference placeholder with structured sections and one example card.
- [x] Add `## Preference Memory Protocol` to `SKILL.md`.
- [x] Explain turn-start preference activation: select 3-7 relevant cards based on current intent.
- [x] Explain Preference Gate before completion.
- [x] Explain candidate preference write-back when the user corrects direction.
- [x] Run `python -m pytest tests/test_high_signal_commander_docs.py tests/test_sync_preference_memory.py -q`.

---

### Task 4: Update README And Run Full Verification

**Files:**
- Modify: `README.md`
- Modify: `.codex/docs/当前任务.md`

- [x] Add `sync_preference_memory.py` to the active implementation list.
- [x] Add a short Preference Memory section under High-Signal usage.
- [x] Update current task checkpoint with final validation evidence.
- [x] Run `python -m pytest -q`.
- [x] Run portable stop gate with pytest evidence.

---

## Self-Review

### Spec Coverage

- Structured preference cards are covered by Tasks 1-3.
- Automatic activation and Preference Gate are covered by Tasks 1 and 3.
- Candidate preference write-back is covered by Tasks 1-3.
- Scripted Markdown write-back is covered by Task 2.
- README product framing is covered by Task 4.

### Type Consistency

- Script name: `sync_preference_memory.py`.
- Function name: `sync_preference_memory`.
- Card id argument: `--id`.
- Card status values: `stable` and `candidate`.
