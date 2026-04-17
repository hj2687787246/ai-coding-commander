[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$CodexHome = (Join-Path $env:USERPROFILE ".codex"),
    [switch]$Force,
    [switch]$BackupExisting
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "This installer requires pwsh / PowerShell 7."
}

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$repoRootPath = (Resolve-Path $RepoRoot).Path
$sourceSkill = Join-Path $repoRootPath "skills/commander-mode"
$targetSkill = Join-Path $CodexHome "skills/commander-mode"
$targetParent = Split-Path -Parent $targetSkill

if (-not (Test-Path -LiteralPath $sourceSkill)) {
    throw "Source skill directory not found: $sourceSkill"
}

$pythonAvailable = $null -ne (Get-Command python -ErrorAction SilentlyContinue)
$backupPath = $null

New-Item -ItemType Directory -Force -Path $targetParent | Out-Null

if (Test-Path -LiteralPath $targetSkill) {
    if ($BackupExisting) {
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupPath = "$targetSkill.backup-$timestamp"
        Move-Item -LiteralPath $targetSkill -Destination $backupPath
    }
    elseif ($Force) {
        Remove-Item -LiteralPath $targetSkill -Recurse -Force
    }
    else {
        throw "Target skill already exists: $targetSkill. Re-run with -Force or -BackupExisting."
    }
}

Copy-Item -LiteralPath $sourceSkill -Destination $targetSkill -Recurse -Force

$result = [ordered]@{
    installed = $true
    target = $targetSkill
    method = "copy"
    pythonAvailable = $pythonAvailable
    backupPath = $backupPath
    nextSteps = @(
        "在新会话里使用 commander-mode",
        "可用 portable_harness.py --cwd . status 检查项目状态",
        "在未初始化项目中可用 bootstrap_codex_workspace.py 创建标准 .codex 骨架"
    )
}

$result | ConvertTo-Json -Depth 4
