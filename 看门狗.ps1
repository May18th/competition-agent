# ============================================================
# 双看门脚本：同时守护 Flask app 和 cpolar
# 哪个挂了自动拉起哪个，保证队友随时能访问
# ============================================================

# Flask app 用哪个 Python（conda 的 rag-dev 环境）
$pythonPath = "C:\Users\34984\.conda\envs\rag-dev\python.exe"
# 项目目录
$projectDir = "C:\Users\34984\Doubao\chats\2026-09-23\new-chat\科创赛事助手"
# 本地端口
$localPort = "8080"
# cpolar 可执行文件（不在 PATH 就改完整路径）
$cpolarPath = "cpolar"

# 用 HTTP 探测判断 app 是否活着（不需要管理员权限）
function Test-AppAlive {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$localPort/" -TimeoutSec 5 -UseBasicParsing
        return $true
    } catch {
        return $false
    }
}

while ($true) {
    # 1) Flask app 挂了就重启
    if (-not (Test-AppAlive)) {
        Write-Host "$(Get-Date) - Flask app 掉了，重启..."
        Start-Process -FilePath $pythonPath -ArgumentList "run.py" `
            -WorkingDirectory $projectDir -WindowStyle Hidden
        Start-Sleep -Seconds 8
    }

    # 2) cpolar 段 —— 2026-09-25 停用（站点已迁阿里云 ECS，固定公网 IP）
    #    保留 Flask 守护，去掉 cpolar 自动重启，防止它复活。

    Start-Sleep -Seconds 30
}
