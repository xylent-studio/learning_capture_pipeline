param(
  [string]$Trigger = 'authorized capture boundary and full autonomy objective',
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

function Write-RehydrateMessage {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Message
  )

  if (-not $Quiet) {
    Write-Host $Message
  }
}

$workspaceRoot = Split-Path -Path $PSScriptRoot -Parent
$intelScriptRoot = 'C:\dev\_intel\scripts'
$resolveScript = Join-Path $intelScriptRoot 'Resolve-AgentContext.ps1'
$restoreScript = Join-Path $intelScriptRoot 'Build-RestoreAnchor.ps1'
$recallScript = Join-Path $intelScriptRoot 'Resolve-RoutedRecall.ps1'
$registerScript = Join-Path $intelScriptRoot 'Register-AgentReentry.ps1'

if (-not (Test-Path -LiteralPath $resolveScript)) {
  Write-RehydrateMessage 'Local intel workspace not found on this machine.'
  Write-RehydrateMessage 'Fallback: read AGENTS.md, README.md, docs\00_project_brief.md, and docs\15_contract_verified_full_autonomy.md before deeper work.'
  exit 0
}

& $resolveScript -TargetPath $workspaceRoot -Profile 'operator-fast' -Quiet | Out-Null

if (Test-Path -LiteralPath $restoreScript) {
  & $restoreScript -TargetPath $workspaceRoot -Profile 'operator-fast' -Quiet | Out-Null
}

if (-not [string]::IsNullOrWhiteSpace($Trigger) -and (Test-Path -LiteralPath $recallScript)) {
  & $recallScript -TargetPath $workspaceRoot -Trigger $Trigger -Profile 'operator-fast' -Quiet | Out-Null
}

if (Test-Path -LiteralPath $registerScript) {
  & $registerScript -TargetPath $workspaceRoot -Trigger $Trigger -Profile 'operator-fast' -EntryPoint 'learning-capture-pipeline-rehydrate-helper' -Quiet | Out-Null
  & $resolveScript -TargetPath $workspaceRoot -Profile 'operator-fast' -Quiet | Out-Null
  if (Test-Path -LiteralPath $restoreScript) {
    & $restoreScript -TargetPath $workspaceRoot -Profile 'operator-fast' -Quiet | Out-Null
  }
}

$runtimeRoot = 'C:\dev\_intel\ops\local-machine-ops'
$contextPath = Join-Path $runtimeRoot 'context-resolutions\learning-capture-pipeline\operator-fast\latest.md'
$restorePath = Join-Path $runtimeRoot 'restore-anchors\learning-capture-pipeline\operator-fast\latest.md'
$recallPath = Join-Path $runtimeRoot 'recall-resolutions\learning-capture-pipeline\operator-fast\latest.md'
$checkpointPath = Join-Path $runtimeRoot 'checkpoints\learning-capture-pipeline\latest.md'
$driftPath = Join-Path $runtimeRoot 'drift-reports\learning-capture-pipeline\latest.md'
$externalContextPath = Join-Path $runtimeRoot 'external-context\learning-capture-pipeline\latest.md'
$externalContextInbox = 'C:\dev\_intel\incoming-context\learning-capture-pipeline\pending'

Write-RehydrateMessage 'Learning Capture Pipeline context refreshed.'
Write-RehydrateMessage ('Target: {0}' -f $workspaceRoot)

foreach ($path in @($contextPath, $restorePath, $recallPath, $checkpointPath, $driftPath, $externalContextPath)) {
  if (Test-Path -LiteralPath $path) {
    Write-RehydrateMessage ('- {0}' -f $path)
  }
}

if (-not (Test-Path -LiteralPath $externalContextPath)) {
  Write-RehydrateMessage ('- external context inbox: {0}' -f $externalContextInbox)
}
