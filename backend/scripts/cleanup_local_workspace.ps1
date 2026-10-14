param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$releaseRoot = Join-Path $Root 'artifacts\releases'
$releaseCurrent = Join-Path $releaseRoot 'current'
$releaseArchive = Join-Path $releaseRoot 'archive\20261015-release-history'
$inspectRoot = Join-Path $Root 'site_inspect'
$inspectArchive = Join-Path $Root 'artifacts\research\site-inspect-20261015'
$qaLegacy = Join-Path $Root 'artifacts\qa\legacy'

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        if ($WhatIf) { Write-Host "CREATE $Path"; return }
        try { New-Item -ItemType Directory -Path $Path -Force | Out-Null }
        catch { Write-Warning "BLOCKED create $Path : $($_.Exception.Message)" }
    }
}

function Move-Safely([string]$Source, [string]$DestinationDir) {
    if (-not (Test-Path -LiteralPath $Source)) { return }
    Ensure-Directory $DestinationDir
    $target = Join-Path $DestinationDir (Split-Path $Source -Leaf)
    if ($WhatIf) { Write-Host "MOVE $Source -> $target"; return }
    try { Move-Item -LiteralPath $Source -Destination $target -Force }
    catch { Write-Warning "BLOCKED move $Source : $($_.Exception.Message)" }
}

Write-Host "Workspace cleanup root: $Root"

# Keep the newest release and one rollback candidate in releases/current.
if (Test-Path -LiteralPath $releaseRoot) {
    $files = @(Get-ChildItem -LiteralPath $releaseRoot -File | Sort-Object LastWriteTime -Descending)
    if ($files.Count -gt 0) {
        Ensure-Directory $releaseCurrent
        Ensure-Directory $releaseArchive
        $keepNames = @($files | Select-Object -First 4 | ForEach-Object Name)
        foreach ($file in $files) {
            if ($keepNames -notcontains $file.Name) {
                Move-Safely $file.FullName $releaseArchive
            } else {
                Move-Safely $file.FullName $releaseCurrent
            }
        }
    }
}

# Remote inspection snapshots are QA material, never runtime input.
if (Test-Path -LiteralPath $inspectRoot) {
    Move-Safely $inspectRoot $inspectArchive
}

# Root-level export probe is not application data.
Move-Safely (Join-Path $Root 'tmp_export.pdf') $qaLegacy

# Python bytecode in archived probes is disposable.
Get-ChildItem -LiteralPath (Join-Path $Root 'backend\archive') -Directory -Filter '__pycache__' -Recurse -ErrorAction SilentlyContinue |
    ForEach-Object {
        if ($WhatIf) { Write-Host "REMOVE $($_.FullName)" }
        else {
            try { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
            catch { Write-Warning "BLOCKED remove $($_.FullName) : $($_.Exception.Message)" }
        }
    }

Write-Host 'Cleanup completed for writable paths.'
Write-Host 'If artifacts/, docs/, or .git remain read-only, rerun this script from an elevated account.'
