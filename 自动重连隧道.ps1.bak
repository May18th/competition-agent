# 自动重连内网穿透脚本
while ($true) {
    $tunnel = Get-Process -Name ssh -ErrorAction SilentlyContinue
    if (-not $tunnel) {
        Write-Host "$(Get-Date) - 隧道断了，重新连接..."
        Start-Process -FilePath ssh -ArgumentList "-o StrictHostKeyChecking=no -R 80:localhost:8080 serveo.net" -WindowStyle Hidden
        Start-Sleep -Seconds 10
        Write-Host "$(Get-Date) - 重新连接完成"
    }
    Start-Sleep -Seconds 30
}
