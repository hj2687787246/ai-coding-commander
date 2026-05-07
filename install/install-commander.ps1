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
$skillNames = @(
    "commander-mode",
    "commander-reuse-upgrader",
    "execution-failure-guard"
)
$targetParent = Join-Path $CodexHome "skills"

foreach ($skillName in $skillNames) {
    $sourceSkill = Join-Path $repoRootPath "skills/$skillName"
    if (-not (Test-Path -LiteralPath $sourceSkill)) {
        throw "Source skill directory not found: $sourceSkill"
    }
}

$pythonAvailable = $null -ne (Get-Command python -ErrorAction SilentlyContinue)
$installedTargets = @()
$backupPaths = @()

New-Item -ItemType Directory -Force -Path $targetParent | Out-Null

foreach ($skillName in $skillNames) {
    $sourceSkill = Join-Path $repoRootPath "skills/$skillName"
    $targetSkill = Join-Path $targetParent $skillName

    if (Test-Path -LiteralPath $targetSkill) {
        if ($BackupExisting) {
            $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $backupPath = "$targetSkill.backup-$timestamp"
            Move-Item -LiteralPath $targetSkill -Destination $backupPath
            $backupPaths += $backupPath
        }
        elseif ($Force) {
            Remove-Item -LiteralPath $targetSkill -Recurse -Force
        }
        else {
            throw "Target skill already exists: $targetSkill. Re-run with -Force or -BackupExisting."
        }
    }

    Copy-Item -LiteralPath $sourceSkill -Destination $targetSkill -Recurse -Force
    $installedTargets += $targetSkill
}

$result = [ordered]@{
    installed = $true
    targets = $installedTargets
    method = "copy"
    pythonAvailable = $pythonAvailable
    backupPaths = $backupPaths
    nextSteps = @(
        "在新会话里使用 commander-mode",
        "重复问题沉淀时使用 commander-reuse-upgrader",
        "命令、工具或环境执行失败并找到可用方法后使用 execution-failure-guard",
        "可用 verify_skill_install.py --repo . --codex-home <path> 确认安装一致性",
        "可用 portable_harness.py --cwd . status 检查项目状态",
        "在未初始化项目中可用 bootstrap_codex_workspace.py 创建标准 .codex 骨架"
    )
}

$result | ConvertTo-Json -Depth 4
