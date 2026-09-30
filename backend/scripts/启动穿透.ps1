# 内网穿透一键启动（服务 + cloudflared 隧道，断线自动重连）
# 用法：右键"使用 PowerShell 运行"，或 powershell -ExecutionPolicy Bypass -File 启动穿透.ps1
# 公网地址看控制台输出，或看 C:\Users\34984\.cloudflared_url.txt

$ErrorActionPreference = "SilentlyContinue"
$PY = "C:\Users\34984\.conda\envs\rag-dev\python.exe"
$CF = "C:\Users\34984\cloudflared.exe"
$BACKEND = "D:\competition-agent\backend"
$URLFILE = "C:\Users\34984\.cloudflared_url.txt"

function Get-UrlFromLog($text) {
    if ($text -match '(https://[a-z0-9-]+\.trycloudflare\.com)') { return $Matches[1] }
    return $null
}

Write-Host "=== 科创赛事助手 内网穿透启动器 ===" -ForegroundColor Cyan

# 1) 本地服务（8080）
$svc = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host "[service] 8080 未监听，启动 run.py ..."
    Start-Process -FilePath $PY -ArgumentList "run.py" -WorkingDirectory $BACKEND -WindowStyle Hidden
    Start-Sleep -Seconds 8
    $svc = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
}
if ($svc) { Write-Host "[service] 8080 OK (PID $($svc[0].OwningProcess))" -ForegroundColor Green }
else { Write-Host "[service] 启动失败，请手动检查: cd $BACKEND && $PY run.py" -ForegroundColor Red; exit 1 }

# 2) cloudflared 隧道（重启后地址会变，写入 $URLFILE）
$cf = Get-Process -Name cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    Write-Host "[tunnel] 启动 cloudflared 快速隧道 ..."
    $log = "$env:TEMP\cloudflared_tunnel.log"
    Start-Process -FilePath $CF -ArgumentList "tunnel","--url","http://localhost:8080","--no-autoupdate" `
        -WindowStyle Hidden -RedirectStandardError $log
    # 等隧道注册（最多 30 秒）
    $url = $null
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 2
        $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
        $url = Get-UrlFromLog $txt
        if ($url) { break }
    }
    if ($url) {
        Set-Content -Path $URLFILE -Value $url -Encoding utf8
        Write-Host "[tunnel] 公网地址: $url" -ForegroundColor Green
        Write-Host "[tunnel] 已存入 $URLFILE"
    } else {
        Write-Host "[tunnel] 30 秒内没拿到地址，看日志: $log" -ForegroundColor Red
    }
} else {
    Write-Host "[tunnel] cloudflared 已在跑 (PID $($cf[0].Id))" -ForegroundColor Green
    if (Test-Path $URLFILE) { Write-Host "[tunnel] 上次地址: $(Get-Content $URLFILE)" }
}

Write-Host ""
Write-Host "=== 完成。手机/外网直接访问上面的 trycloudflare.com 地址 ===" -ForegroundColor Cyan
Write-Host "注意：快速隧道无固定域名，cloudflared 重启后地址会变（新地址会更新到 $URLFILE）"
