#!/usr/bin/env bash
# ============================================================================
# deploy_safe.sh —— 四段式安全部署：备份 → 同步 → 验证 → 自动回滚
#
# 背景：用户部署纪律——"没有部署前备份、部署后验证、自动回滚，随时可能再断"。
# 任何一步失败都不允许让线上停在半部署状态。
#
# 【用法示例】
#   # 1) 默认部署（前端正式静态资源 + 后端代码/依赖 + data/knowledge_base 只读知识源）
#   bash backend/scripts/deploy_safe.sh
#
#   # 2) 只看将同步什么（不实际传输、不重启、不验证）
#   bash backend/scripts/deploy_safe.sh --dry-run
#
#   # 3) 自定义文件列表（相对仓库根的路径，可含通配符）
#   bash backend/scripts/deploy_safe.sh --files "frontend/index.html backend/app.py"
#
#   # 4) 临时换目标服务器（不改脚本）
#   WB_SSH_HOST=root@1.2.3.4 WB_SSH_KEY=~/.ssh/other_key bash backend/scripts/deploy_safe.sh
#
# 【可配置环境变量】（括号内为默认值，均查实自项目笔记与代码）
#   WB_SSH_HOST        SSH 目标（root@8.149.236.90，见 C:/Users/34984/ssh_aliyun.sh）
#   WB_SSH_KEY         SSH 私钥（~/.ssh/id_aliyun_deploy）
#   WB_SSH_PORT        SSH 端口（22）
#   WB_REMOTE_DIR      远端项目根（/opt/comp-agent）
#   WB_BACKUP_DIR      远端备份目录（/opt/backups，不存在自动创建）
#   WB_DB_PATH         SQLite 路径（留空=自动探测：优先 backend/competition.db，
#                      兜底 <REMOTE_DIR>/competition.db 旧位置）
#   WB_SITE_URL        站点地址（https://kechuang2026.cn）
#   WB_STATIC_URL      静态资源验证地址（$WB_SITE_URL/static/app.js）
#   WB_SERVICE         systemd 服务名（comp-agent）
#
# 【查实依据】
#   - DB 路径：backend/run.py:4-15（运行时文件归属 backend/，启动 chdir 钉死）；
#     backend/kb_samples.py:13 / backend/distill_scheduler.py:19 同证。
#     2026-10-01 实测线上为旧布局：DB 实际在 <REMOTE_DIR>/competition.db，
#     backend/competition.db 不存在 —— 故脚本内置双路径探测，两处都覆盖。
#   - 健康路由：backend/app.py:5505 @app.route('/api/health')，返回 {"success":true,"status":"ok",...}
#   - 服务/路径：环境与常用命令笔记.md「阿里云 ECS」节：systemctl restart comp-agent、/opt/comp-agent。
#
# 【回滚语义】
#   备份 tar 只含代码与静态资源（排除 .git/.venv/uploads/DB/.env 等运行时数据）；
#   DB 另做独立热备份（优先 sqlite3 backup API，失败退化为 cp）。
#   回滚 = 解包 tar 覆盖代码 + 重启服务 + 复验；DB 不被回滚覆盖（部署同步列表本就不含 DB）。
# ============================================================================
set -euo pipefail

# ---------- 可配置项（环境变量优先） ----------
SSH_HOST="${WB_SSH_HOST:-root@8.149.236.90}"
SSH_KEY="${WB_SSH_KEY:-$HOME/.ssh/id_aliyun_deploy}"
SSH_PORT="${WB_SSH_PORT:-22}"
REMOTE_DIR="${WB_REMOTE_DIR:-/opt/comp-agent}"
BACKUP_DIR="${WB_BACKUP_DIR:-/opt/backups}"
DB_PATH="${WB_DB_PATH:-}"                # 留空则自动探测
SITE_URL="${WB_SITE_URL:-https://kechuang2026.cn}"
STATIC_URL="${WB_STATIC_URL:-${SITE_URL}/static/app.js}"
SERVICE="${WB_SERVICE:-comp-agent}"
RESTART_WAIT="${WB_RESTART_WAIT:-5}"     # restart 后等待秒数（对齐 deploy_guard.py 的 sleep 5）

SSH_CMD="ssh -i $SSH_KEY -p $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15"
# 数组形式：--noproxy 的 '*' 若用无引号字符串展开会被 glob 污染，必须数组+引号
CURL_OPTS=(-sk --noproxy '*' --max-time 30)   # -k: nginx 自签/透明链路; --noproxy: 本机代理会劫持外网请求

# ---------- 参数解析 ----------
DRY_RUN=0
# 仅同步代码、依赖、正式前端资源和只读知识源。运行数据/凭据（DB、上传、生成物、
# official_docs.json、.env、.uid_secret、quota.json、chroma_db、训练库）不在此列表，
# 即使本地存在也不会被覆盖到线上。静态资源按扩展名匹配，避免把 tmp_*.html 探针上传。
FILES_RAW="frontend/index.html frontend/科创赛事助手.ico frontend/static/*.css frontend/static/*.js frontend/static/*.json frontend/static/*.png frontend/static/*.ico backend/*.py backend/requirements.txt backend/Procfile backend/Dockerfile backend/data/*.txt backend/data/competition_profiles.json backend/data/event_requirements.json backend/data/README_知识库提交规范.md backend/knowledge_base/*.json backend/knowledge_base/*.txt"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --files) FILES_RAW="$2"; shift 2 ;;
    -h|--help) sed -n '2,43p' "$0" | sed 's/^#\{1,2\} \{0,1\}//'; exit 0 ;;
    *) echo "[SYNC] 未知参数: $1（用法见脚本头部注释，或 --help）" >&2; exit 2 ;;
  esac
done

# ---------- 通用函数 ----------
ssh_run() { $SSH_CMD "$SSH_HOST" "$@"; }

die() { echo "[SYNC] FATAL: $*" >&2; exit 3; }

# 优先等待运行中的生成任务结束再重启；兼容前后端分离后的
# $REMOTE_DIR/backend/scripts/ 路径和旧版 $REMOTE_DIR/scripts/ 路径。
restart_remote() {
  if ssh_run "test -x '$REMOTE_DIR/scripts/safe_restart.sh'"; then
    echo "[SYNC] 使用远端安全重启脚本: $REMOTE_DIR/scripts/safe_restart.sh"
    ssh_run "'$REMOTE_DIR/scripts/safe_restart.sh' '${WB_RESTART_MAX_WAIT:-600}'"
  elif ssh_run "test -x '$REMOTE_DIR/backend/scripts/safe_restart.sh'"; then
    echo "[SYNC] 使用远端安全重启脚本: $REMOTE_DIR/backend/scripts/safe_restart.sh"
    ssh_run "'$REMOTE_DIR/backend/scripts/safe_restart.sh' '${WB_RESTART_MAX_WAIT:-600}'"
  else
    if [ "${WB_ALLOW_UNSAFE_RESTART:-0}" = "1" ]; then
      echo "[SYNC] 警告：远端未找到 safe_restart.sh，按显式授权回退 systemctl restart $SERVICE" >&2
      ssh_run "systemctl restart '$SERVICE'"
    else
      echo "[SYNC] FATAL: 远端未找到 safe_restart.sh；为避免打断生成任务，拒绝裸重启。" >&2
      echo "[SYNC] 如已确认没有运行中的生成任务，才可显式设置 WB_ALLOW_UNSAFE_RESTART=1。" >&2
      return 1
    fi
  fi
}

rollback_and_exit() {
  # $1=退出码 $2=原因
  echo "[ROLLBACK] 触发原因: $2"
  if [ -z "${BACKUP_TARBALL:-}" ]; then
    echo "[ROLLBACK] 尚无可用备份（pre_backup 未完成），未同步过任何文件，直接退出" >&2
    exit 1
  fi
  echo "[ROLLBACK] 解包最近备份恢复代码: $BACKUP_TARBALL"
  if ! ssh_run "tar -xzf '$BACKUP_TARBALL' -C /opt"; then
    echo "[ROLLBACK] FATAL: 备份解包失败，线上状态未知，请立即人工介入！" >&2
    exit 2
  fi
  echo "[ROLLBACK] 重启服务 $SERVICE"
  restart_remote
  sleep "$RESTART_WAIT"
  code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$SITE_URL/api/health" || echo 000)
  if [ "$code" = "200" ]; then
    echo "[ROLLBACK] 回滚完成，服务已恢复健康（原部署判定为失败，退出码 1）"
    exit 1
  else
    echo "[ROLLBACK] FATAL: 回滚后 /api/health 仍返回 $code，服务未恢复，请立即人工介入！" >&2
    exit 2
  fi
}

# ---------- 第 0 步：本地预检 ----------
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

# 展开通配符并逐个校验存在性（不存在 = 名单写错，宁可拒绝开工）
SYNC_FILES=()
for f in $FILES_RAW; do
  [ -f "$f" ] || die "文件列表中存在不存在的文件: $f（相对仓库根 $REPO_ROOT）"
  SYNC_FILES+=("$f")
done
[ ${#SYNC_FILES[@]} -gt 0 ] || die "文件列表为空"

# 即使调用方通过 --files 自定义名单，也不允许把线上运行数据、凭据或机器相关
# 索引带上去。这个守卫必须在 SSH、备份和传输之前执行。
for f in "${SYNC_FILES[@]}"; do
  case "$f" in
    *competition.db*|*official_docs.json|uploads/*|*/uploads/*|generated/*|*/generated/*|tmp_export/*|*/tmp_export/*|\
    *.env|*.uid_secret|*admin_users.json|*quota.json|*/chroma_db/*|*/训练库/*|\
    *.log|frontend/static/tmp_*)
      die "禁止同步运行数据/凭据/临时文件: $f"
      ;;
  esac
done

echo "[BACKUP] 仓库根: $REPO_ROOT"
echo "[BACKUP] 目标: $SSH_HOST:$REMOTE_DIR，共 ${#SYNC_FILES[@]} 个文件待同步"

# dry-run 在任何 SSH/远端备份之前结束，确保“预演”不会创建远端文件或触碰线上数据。
if [ "$DRY_RUN" = "1" ]; then
  echo "[SYNC] --dry-run 模式：以下为将要同步的文件（不连接远端、不传输、不重启、不验证）"
  for f in "${SYNC_FILES[@]}"; do echo "[SYNC]   $f -> $REMOTE_DIR/$f"; done
  echo "[SYNC] dry-run 结束。线上未发生任何改动。"
  exit 0
fi

echo "[BACKUP] 测试 SSH 连通性..."
ssh_run "echo ok" >/dev/null || die "SSH 连接失败（$SSH_HOST），部署未开始，无任何改动"

# ---------- 第 1 段：pre_backup（部署前备份） ----------
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_TARBALL="$BACKUP_DIR/comp-agent_${TS}.tar.gz"
DB_BAK="$BACKUP_DIR/competition_db_${TS}.bak"

# DB 路径探测（0930 重构后归属 backend/，旧部署可能仍在根目录）
if [ -z "$DB_PATH" ]; then
  if ssh_run "test -f '$REMOTE_DIR/backend/competition.db'"; then
    DB_PATH="$REMOTE_DIR/backend/competition.db"
  elif ssh_run "test -f '$REMOTE_DIR/competition.db'"; then
    DB_PATH="$REMOTE_DIR/competition.db"
  else
    DB_PATH=""
  fi
fi

echo "[BACKUP] 创建备份目录 $BACKUP_DIR"
ssh_run "mkdir -p '$BACKUP_DIR'"

echo "[BACKUP] 打包代码: $BACKUP_TARBALL（排除 .git/.venv/__pycache__/uploads/generated/tmp_export/DB/.env）"
ssh_run "tar -czf '$BACKUP_TARBALL' \
  --exclude='comp-agent/.git' \
  --exclude='comp-agent/.venv' \
  --exclude='comp-agent/backend/.venv' \
  --exclude='comp-agent/backend/__pycache__' \
  --exclude='comp-agent/__pycache__' \
  --exclude='comp-agent/uploads' \
  --exclude='comp-agent/backend/uploads' \
  --exclude='comp-agent/generated' \
  --exclude='comp-agent/backend/generated' \
  --exclude='comp-agent/backend/tmp_export' \
  --exclude='comp-agent/competition.db' \
  --exclude='comp-agent/backend/competition.db' \
  --exclude='comp-agent/.env' \
  --exclude='comp-agent/backend/.env' \
  --exclude='*.log' \
  -C /opt comp-agent"
ssh_run "test -s '$BACKUP_TARBALL'" || die "备份 tar 生成失败或为空文件，中止部署（线上未动）"
echo "[BACKUP] 代码备份完成: $(ssh_run "du -h '$BACKUP_TARBALL'" | cut -f1)"

if [ -n "$DB_PATH" ]; then
  echo "[BACKUP] 单独热备份 DB: $DB_PATH -> $DB_BAK"
  # 优先用项目自带 venv 的 sqlite3 backup API（一致性快照），失败退化为 cp
  ssh_run "'$REMOTE_DIR/.venv/bin/python' -c 'import sqlite3,sys; \
s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()' \
'$DB_PATH' '$DB_BAK' 2>/dev/null || cp '$DB_PATH' '$DB_BAK'"
  ssh_run "test -s '$DB_BAK'" || die "DB 备份失败，中止部署（线上未动）"
  echo "[BACKUP] DB 备份完成: $(ssh_run "du -h '$DB_BAK'" | cut -f1)"
else
  echo "[BACKUP] 未发现 SQLite DB 文件，跳过 DB 备份"
fi

# ---------- 第 2 段：sync（同步文件） ----------
echo "[SYNC] 同步 ${#SYNC_FILES[@]} 个文件到 $SSH_HOST:$REMOTE_DIR"
if command -v rsync >/dev/null 2>&1; then
  # -R 保留相对路径层级；一次传输全部文件
  if ! rsync -avR -e "$SSH_CMD" "${SYNC_FILES[@]}" "$SSH_HOST:$REMOTE_DIR/"; then
    rollback_and_exit 1 "rsync 同步失败（远端可能处于半同步状态）"
  fi
else
  echo "[SYNC] 本机无 rsync，退化用 scp 逐文件传输"
  for f in "${SYNC_FILES[@]}"; do
    dest_dir="$REMOTE_DIR/$(dirname "$f")"
    ssh_run "mkdir -p '$dest_dir'" || rollback_and_exit 1 "创建远端目录失败: $dest_dir"
    if ! scp -i "$SSH_KEY" -P "$SSH_PORT" \
         -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
         "$f" "$SSH_HOST:$dest_dir/"; then
      rollback_and_exit 1 "scp 传输失败: $f"
    fi
    echo "[SYNC]   OK: $f"
  done
fi
echo "[SYNC] 同步完成"

echo "[SYNC] 安全重启服务 $SERVICE（等待进行中的生成任务）"
restart_remote || rollback_and_exit 1 "安全重启失败"
sleep "$RESTART_WAIT"

# ---------- 第 3 段：verify（部署后验证） ----------
VERIFY_FAILED=0
verify_fail() { echo "[VERIFY] FAIL: $*" >&2; VERIFY_FAILED=$((VERIFY_FAILED + 1)); }

echo "[VERIFY] 1/5 逐文件 md5sum 对比（本地 vs 远端）"
for f in "${SYNC_FILES[@]}"; do
  local_sum=$(md5sum "$f" | cut -d' ' -f1)
  remote_sum=$(ssh_run "md5sum '$REMOTE_DIR/$f' 2>/dev/null" | cut -d' ' -f1)
  if [ -z "$remote_sum" ]; then
    verify_fail "$f 远端不存在（md5sum 无输出）"
  elif [ "$local_sum" != "$remote_sum" ]; then
    verify_fail "$f md5 不一致: 本地=${local_sum:0:8}.. 远端=${remote_sum:0:8}.."
  else
    echo "[VERIFY]   OK: $f (${local_sum:0:8}...)"
  fi
done

echo "[VERIFY] 2/5 首页 HTTP 状态"
code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$SITE_URL/" || echo 000)
[ "$code" = "200" ] && echo "[VERIFY]   OK: $SITE_URL/ -> 200" || verify_fail "首页 $SITE_URL/ 返回 $code"

echo "[VERIFY] 3/5 健康接口（/api/health）"
code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$SITE_URL/api/health" || echo 000)
body=$(curl "${CURL_OPTS[@]}" "$SITE_URL/api/health" || true)
if [ "$code" = "200" ] && echo "$body" | grep -q '"status"'; then
  echo "[VERIFY]   OK: /api/health -> 200, body 含 status 字段"
else
  verify_fail "/api/health 异常: HTTP=$code, body=${body:0:80}"
fi

echo "[VERIFY] 4/5 静态资源（带版本参数防缓存）"
code=$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "${STATIC_URL}?v=${TS}" || echo 000)
[ "$code" = "200" ] && echo "[VERIFY]   OK: ${STATIC_URL}?v=${TS} -> 200" || verify_fail "静态资源 $STATIC_URL 返回 $code"

echo "[VERIFY] 5/5 systemd 服务状态"
svc=$(ssh_run "systemctl is-active '$SERVICE'" || true)
[ "$svc" = "active" ] && echo "[VERIFY]   OK: $SERVICE is-active" || verify_fail "$SERVICE 状态为 '$svc'（期望 active）"

if [ "$VERIFY_FAILED" -gt 0 ]; then
  rollback_and_exit 1 "verify 有 $VERIFY_FAILED 项失败"
fi

echo "[VERIFY] 全部验证通过。本次备份: $BACKUP_TARBALL"
echo "[SYNC] 部署成功: $TS，${#SYNC_FILES[@]} 个文件已上线。"
exit 0
