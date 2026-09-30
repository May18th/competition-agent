# ============================================================
# cpolar 自动重连脚本（防隧道掉线）
# 作用：cpolar 进程挂掉时自动重启，保证队友能持续访问
# 前提：Flask app 已在 8080 运行（python run.py）
# ============================================================

# cpolar 可执行文件：如果在 PATH 里直接用 "cpolar"；
# 否则改成完整路径，例如 "C:\Program Files\cpolar\cpolar.exe"
$cpolarPath = "cpolar"

# 本地要暴露的端口
$localPort = "8080"

while ($true) {
    $tunnel = Get-Process -Name "cpolar" -ErrorAction SilentlyContinue
    if (-not $tunnel) {
        Write-Host "$(Get-Date) - cpolar 掉了，重新启动..."
        # 命令行方式：cpolar http 8080
        # 如果你用的是「命名隧道」，改成下面这行（去掉 #）：
        #   Start-Process -FilePath $cpolarPath -ArgumentList @("tunnel", "start", "<你的隧道名>") -WindowStyle Hidden
        Start-Process -FilePath $cpolarPath -ArgumentList @("http", $localPort) -WindowStyle Hidden
        Start-Sleep -Seconds 10
        Write-Host "$(Get-Date) - 重启完成"
    }
    Start-Sleep -Seconds 30
}
