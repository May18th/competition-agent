param(
    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $OutputPath = Join-Path $Root "artifacts\releases\competition-agent-release-$stamp.tar.gz"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

$manifest = [System.Collections.Generic.List[string]]::new()
function Add-RelativeFile([string]$Path) {
    $full = (Resolve-Path -LiteralPath (Join-Path $Root $Path)).Path
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "发布文件不存在: $Path"
    }
    [void]$manifest.Add($full.Substring($Root.Length + 1).Replace('\', '/'))
}
function Add-RelativeDirectoryFiles([string]$Directory, [string[]]$Extensions, [string[]]$ExcludeNames = @()) {
    Get-ChildItem -LiteralPath (Join-Path $Root $Directory) -File |
        Where-Object {
            $_.Extension.ToLowerInvariant() -in $Extensions -and
            $_.Name -notlike 'tmp_*' -and
            $_.Name -notin $ExcludeNames
        } |
        ForEach-Object { Add-RelativeFile $_.FullName.Substring($Root.Length + 1) }
}

@(
    'frontend/index.html',
    'backend/requirements.txt',
    'backend/Procfile',
    'backend/Dockerfile',
    'backend/scripts/safe_restart.sh',
    'backend/scripts/deploy_safe.sh'
) | ForEach-Object { Add-RelativeFile $_ }

# Avoid a non-ASCII icon filename here: Windows PowerShell may decode UTF-8
# scripts without a BOM using the local code page.
foreach ($icon in @(Get-ChildItem -LiteralPath (Join-Path $Root 'frontend') -File -Filter '*.ico')) {
    Add-RelativeFile $icon.FullName.Substring($Root.Length + 1)
}

Add-RelativeDirectoryFiles 'frontend/static' @('.css', '.js', '.json', '.png', '.ico')
Get-ChildItem -LiteralPath (Join-Path $Root 'backend') -File -Filter '*.py' |
    ForEach-Object { Add-RelativeFile $_.FullName.Substring($Root.Length + 1) }
Add-RelativeDirectoryFiles 'backend/data' @('.txt', '.json') @('official_docs.json', 'vulns.json')
Add-RelativeDirectoryFiles 'backend/knowledge_base' @('.txt', '.json')

$manifest = @($manifest | Sort-Object -Unique)
$forbidden = @($manifest | Where-Object {
    $_ -match 'competition\.db|official_docs\.json|uploads|generated|tmp_export|\.env|uid_secret|admin_users|quota|chroma_db|训练库|(^|/)tmp_'
})
if ($forbidden.Count -gt 0) {
    throw "发布清单包含禁止文件: $($forbidden -join ', ')"
}

$manifestFile = [System.IO.Path]::ChangeExtension($OutputPath, '.manifest.txt')
$manifest | Set-Content -LiteralPath $manifestFile -Encoding UTF8
$tarArgs = @('-czf', $OutputPath, '-C', $Root) + $manifest
& tar.exe @tarArgs
if ($LASTEXITCODE -ne 0) {
    throw "tar 打包失败，退出码: $LASTEXITCODE"
}
$entries = @(& tar.exe -tzf $OutputPath)
if ($entries.Count -ne $manifest.Count) {
    throw "压缩包条目数不一致: manifest=$($manifest.Count), archive=$($entries.Count)"
}

$hash = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash
Write-Output "发布文件数: $($manifest.Count)"
Write-Output "发布包: $OutputPath"
Write-Output "清单: $manifestFile"
Write-Output "SHA256: $hash"
