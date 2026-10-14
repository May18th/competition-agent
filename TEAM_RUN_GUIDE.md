# 可创无限代码包运行说明

本说明适用于 `competition-agent-release` 代码包。代码包只包含程序代码和前端资源，不包含数据库、`.env`、上传文件、历史生成物或服务器密钥。

## 目录检查

解压后，项目根目录应直接包含：

```text
backend/
frontend/
TEAM_RUN_GUIDE.md
```

不要在项目根目录外再套一层目录，也不要直接运行 `backend/app.py`。

## Windows 本地运行

在项目根目录打开 PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\pip.exe install -r backend\requirements.txt
```

配置模型密钥：

```powershell
$env:DEEPSEEK_API_KEY="替换为实际的 DeepSeek API Key"
$env:DEEPSEEK_MODEL="deepseek-flash"
```

启动开发服务：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

浏览器打开 `http://127.0.0.1:8080`。

## Linux / macOS 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

export DEEPSEEK_API_KEY="替换为实际的 DeepSeek API Key"
export DEEPSEEK_MODEL=deepseek-flash

python backend/run.py
```

浏览器打开 `http://127.0.0.1:8080`。

## 健康检查

服务启动后执行：

```bash
curl http://127.0.0.1:8080/api/health
```

正常状态应包含：

```json
{"ready": true, "status": "ok"}
```

如果 `model_reachable` 为 `false`，优先检查 `DEEPSEEK_API_KEY`、网络和模型名称；基础页面仍可能可以打开，但生成能力不可用。

## Linux 生产启动

进入后端目录并确保虚拟环境已经安装依赖：

```bash
cd backend
../.venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8080 --workers 1 --threads 4 --timeout 600
```

必须使用单 worker。任务进度和生成状态保存在进程内存中，多 worker 会导致提交和轮询落到不同进程。

## 常见问题

- `No module named ...`：确认已在项目根目录执行依赖安装。
- 端口被占用：先停止占用 8080 的进程，或使用 Gunicorn 改绑定端口。
- 页面能打开但无法生成：检查 `DEEPSEEK_API_KEY` 和 `/api/health` 返回值。
- 不要把 `competition.db`、`.env`、上传目录或生成目录上传到代码仓库或共享包。
