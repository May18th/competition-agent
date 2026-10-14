# 阿里云 Workbench 直传迁移

这份流程用于把本地发布包直接传到阿里云 ECS，不经过 GitHub。目标目录默认是
`/opt/comp-agent`，服务名是 `comp-agent`。所有命令都在 ECS Workbench 的 root 终端执行。

## 1. 上传与校验

在 Workbench 的文件上传入口，把本地文件

```text
D:\competition-agent\artifacts\releases\competition-agent-release-20261002-final17.zip
```

上传到服务器 `/tmp/competition-agent-release-20261002-final17.zip`。上传后先校验，校验不通过就停止：

```bash
ZIP=/tmp/competition-agent-release-20261002-final17.zip
printf '4E233104C769274CB10E132604DC81A4B2D3121CC650753F64296BC96C7270CB  %s\n' "$ZIP" | sha256sum -c -
```

当前包的 SHA-256 会在本地打包后写入这里：

```text
4E233104C769274CB10E132604DC81A4B2D3121CC650753F64296BC96C7270CB
```

## 2. 只读探测线上布局

先执行以下命令，不会修改线上文件：

```bash
APP=/opt/comp-agent
printf 'layout='
if [ -f "$APP/backend/app.py" ]; then
  echo backend
elif [ -f "$APP/app.py" ] || [ -d "$APP/static" ]; then
  echo legacy
else
  echo empty
fi
printf 'service='
systemctl is-active comp-agent 2>/dev/null || true
systemctl cat comp-agent 2>/dev/null | sed -n '1,100p'
find "$APP" -maxdepth 2 -type f \( -name 'competition.db' -o -name '.env' -o -name 'app.py' -o -name 'wsgi.py' -o -name 'index.html' \) -print
```

旧线上通常是 `legacy`：`app.py`、`index.html`、`static/` 和 `competition.db` 在项目根目录。
当前代码是 `backend` 布局：入口为 `backend/wsgi.py`，数据库和运行目录在 `backend/`。

## 3. 解包到临时目录

临时目录只用于读取发布包，不要直接在 `/opt/comp-agent` 解压：

```bash
STAGE=$(mktemp -d /tmp/comp-agent-release.XXXXXX)
unzip -q "$ZIP" -d "$STAGE"
test -f "$STAGE/backend/wsgi.py" && test -f "$STAGE/frontend/index.html" && echo STAGE_OK
```

## 4. 迁移纪律

发布包只包含代码、前端静态资源和只读知识源。以下线上数据永远由服务器保留，不能用本地同名文件覆盖：

```text
competition.db
uploads/
generated/
tmp_export/
.env
.uid_secret
.admin_users.json
quota.json
notice.json
data/official_docs.json
chroma_db/
训练库/
```

legacy 迁移到 backend 时，不搬动这些数据；如果 `backend/` 目标不存在，则创建指向根目录原数据的相对软链接。例如 `backend/competition.db -> ../competition.db`。这样新入口继续使用原用户历史、上传和生成物，回滚到旧入口也不会丢数据。

若根目录和 `backend/` 同名数据同时存在但内容不同，必须停止并人工核对：

```bash
cmp -s "$APP/competition.db" "$APP/backend/competition.db" || echo 'CONFLICT: database copies differ'
```

不得用 `cp`、`mv`、`git reset --hard` 或 `git pull` 解决冲突。

## 5. 发布前备份

先等待 `/tmp/comp_agent_gens` 归零，再停服务。备份目录只允许 root 读取：

```bash
APP=/opt/comp-agent
TS=$(date +%Y%m%d_%H%M%S)
B=/opt/backups/comp-agent_$TS
install -d -m 700 "$B"
systemctl cat comp-agent > "$B/comp-agent.service.before" 2>/dev/null || true
tar -czf "$B/code-before.tar.gz" -C /opt \
  --exclude='comp-agent/.git' --exclude='comp-agent/.venv' \
  --exclude='comp-agent/competition.db' --exclude='comp-agent/backend/competition.db' \
  --exclude='comp-agent/uploads' --exclude='comp-agent/backend/uploads' \
  --exclude='comp-agent/generated' --exclude='comp-agent/backend/generated' \
  --exclude='comp-agent/tmp_export' --exclude='comp-agent/backend/tmp_export' \
  --exclude='comp-agent/.env' --exclude='comp-agent/backend/.env' \
  --exclude='comp-agent/.uid_secret' --exclude='comp-agent/backend/.uid_secret' \
  --exclude='comp-agent/.admin_users.json' --exclude='comp-agent/backend/.admin_users.json' \
  --exclude='comp-agent/data/official_docs.json' --exclude='comp-agent/backend/data/official_docs.json' \
  comp-agent
echo "代码备份：$B/code-before.tar.gz"
```

数据库另做一致性备份。优先使用项目虚拟环境的 Python，缺失时使用系统 Python：

```bash
PY="$APP/.venv/bin/python"
[ -x "$PY" ] || PY=$(command -v python3)
DB=""
[ -f "$APP/backend/competition.db" ] && DB="$APP/backend/competition.db"
[ -n "$DB" ] || { [ -f "$APP/competition.db" ] && DB="$APP/competition.db" || true; }
if [ -n "$DB" ]; then
  "$PY" - "$DB" "$B/competition.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
PY
  chmod 600 "$B/competition.db"
fi
```

## 6. 安装代码并切换入口

先在停服务前检查已有数据是否冲突。文件相同可以继续；两份不同必须停止并人工核对：

```bash
same_or_abort() {
  src="$1"; dst="$2"
  [ -e "$src" ] && [ -e "$dst" ] || return 0
  if [ -f "$src" ] && [ -f "$dst" ] && cmp -s "$src" "$dst"; then
    echo "same $src $dst"
  else
    echo "CONFLICT: $src and $dst both exist; abort without overwrite" >&2
    exit 5
  fi
}
same_or_abort "$APP/competition.db" "$APP/backend/competition.db"
for x in .uid_secret .admin_users.json quota.json notice.json; do
  same_or_abort "$APP/$x" "$APP/backend/$x"
done
for x in uploads generated tmp_export chroma_db 训练库; do
  if [ -d "$APP/$x" ] && [ -d "$APP/backend/$x" ] \
      && [ ! -L "$APP/$x" ] && [ ! -L "$APP/backend/$x" ]; then
    echo "CONFLICT: both $APP/$x and $APP/backend/$x are real directories; abort" >&2
    exit 5
  fi
done
```

确认没有冲突且没有运行中的生成任务后再执行：

```bash
MARK=/tmp/comp_agent_gens
for i in $(seq 1 120); do
  n=$(cat "$MARK" 2>/dev/null || echo 0)
  [ "$n" -le 0 ] && break
  echo "running=$n wait=$((i*5))s"
  sleep 5
done
[ "$(cat "$MARK" 2>/dev/null || echo 0)" -le 0 ] || { echo '生成任务仍在运行，已中止'; exit 4; }

WAS_ACTIVE=0
systemctl is-active --quiet comp-agent && WAS_ACTIVE=1
if [ "$WAS_ACTIVE" = 1 ]; then
  systemctl stop comp-agent || { echo '停止服务失败，未复制代码'; exit 7; }
fi

mkdir -p "$APP/frontend" "$APP/backend"
cp -a "$STAGE/frontend/." "$APP/frontend/"
cp -a "$STAGE/backend/." "$APP/backend/"
```

在复制代码后，只给缺失的 backend 运行路径建立软链接；已有目标不覆盖：

```bash
link_if_missing() {
  src="$1"; dst="$2"; rel="$3"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    echo "keep $dst"
  elif [ -e "$src" ] || [ -L "$src" ]; then
    ln -s "$rel" "$dst"
    echo "link $dst -> $rel"
  fi
}
link_if_missing "$APP/competition.db" "$APP/backend/competition.db" ../competition.db
for x in uploads generated tmp_export chroma_db 训练库; do
  link_if_missing "$APP/$x" "$APP/backend/$x" "../$x"
done
for x in .uid_secret .admin_users.json quota.json notice.json; do
  link_if_missing "$APP/$x" "$APP/backend/$x" "../$x"
done
link_if_missing "$APP/data/official_docs.json" "$APP/backend/data/official_docs.json" ../../data/official_docs.json
```

`.env` 不复制、不改名，继续由旧 systemd unit 的 `EnvironmentFile` 或 `Environment` 提供。

切换 systemd 只修改工作目录和 WSGI 入口，不改服务密钥：

```bash
test -x "$APP/.venv/bin/gunicorn" || { echo '缺少 .venv/bin/gunicorn，先安装依赖，未写服务配置'; exit 6; }
install -d /etc/systemd/system/comp-agent.service.d
cat >/etc/systemd/system/comp-agent.service.d/10-backend-layout.conf <<'EOF'
[Service]
WorkingDirectory=/opt/comp-agent/backend
ExecStart=
ExecStart=/opt/comp-agent/.venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8080 --workers 1 --threads 4 --timeout 600
EOF
systemctl daemon-reload
if [ "$WAS_ACTIVE" = 1 ]; then
  systemctl start comp-agent || { echo '服务启动失败，保留备份目录和现场'; journalctl -u comp-agent -n 80 --no-pager; exit 8; }
fi
```

## 7. 发布后验证

```bash
sleep 5
systemctl is-active comp-agent
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS http://127.0.0.1:8080/api/memory | head -c 300
```

然后从公网检查首页、登录/后台、历史记录、一次简洁生成、一次局部修改和 Word/PDF/PPT/ZIP 导出。

若服务未恢复，先保留 `$B` 目录和 `journalctl -u comp-agent -n 200 --no-pager` 输出，不要删除现场；可用备份代码恢复后再排查。该流程不使用 GitHub，不上传数据库，不覆盖用户材料。
