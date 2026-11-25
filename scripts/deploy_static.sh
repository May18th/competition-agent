#!/usr/bin/env bash
# 静态文件安全上线：基线比对 → 备份 → 上传 → 校验
#
# 为什么需要它：2026-11-25 13:14 线上 index.html / app.js 被整文件覆盖，没留任何备份，
# 事后无法回溯那次覆盖带走了什么。这个脚本把「先备份、再覆盖、后校验」变成默认动作。
#
# 用法：
#   scripts/deploy_static.sh frontend/index.html frontend/static/app.js
#   scripts/deploy_static.sh --dry-run frontend/static/wbchat.js    # 只看差异，不动线上
#
# 覆盖的环境变量：
#   DEPLOY_HOST   默认 root@8.149.236.90
#   DEPLOY_KEY    默认 ~/.ssh/id_aliyun_deploy
#   REMOTE_DIR    默认 /opt/comp-agent
#
# 说明：
# - 静态文件（index.html / static/*）每次请求读盘，上传即生效，不需要重启服务；
# - 但带 ?v= 的引用要自己 bump 版本号，否则老访客拿缓存；脚本会在结尾提醒；
# - 路径映射：frontend/X → /opt/comp-agent/X，frontend/static/X → /opt/comp-agent/static/X。

set -euo pipefail

HOST="${DEPLOY_HOST:-root@8.149.236.90}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/id_aliyun_deploy}"
RDIR="${REMOTE_DIR:-/opt/comp-agent}"
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10)

DRY=0
FILES=()
for a in "$@"; do
    case "$a" in
        --dry-run) DRY=1 ;;
        -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
        *) FILES+=("$a") ;;
    esac
done

if [ ${#FILES[@]} -eq 0 ]; then
    echo "用法：$0 [--dry-run] <本地路径> [更多路径...]" >&2
    exit 2
fi
[ -f "$KEY" ] || { echo "!! SSH 密钥不存在：$KEY" >&2; exit 1; }

TS=$(date +%Y%m%d-%H%M%S)
TMP="$(dirname "$0")/../.workbuddy/tmp_deploy"
mkdir -p "$TMP"
CHANGED=0
SKIPPED=0
FAILED=0

md5_of() { md5sum "$1" | awk '{print $1}'; }

for f in "${FILES[@]}"; do
    [ -f "$f" ] || { echo "!! 本地文件不存在：$f" >&2; FAILED=$((FAILED+1)); continue; }

    # frontend/ 前缀 → 线上根；其余按相对路径直接映射
    rel="${f#./}"
    rel="${rel#frontend/}"
    rpath="$RDIR/$rel"

    base="$TMP/$(echo "$rel" | tr '/' '_').baseline"
    scp -q "${SSH_OPTS[@]}" "$HOST:$rpath" "$base" 2>/dev/null || {
        echo "!! 线上不存在或拉不到：$rpath" >&2
        FAILED=$((FAILED+1)); continue
    }
    local_md5=$(md5_of "$f")
    remote_md5=$(md5_of "$base")

    if [ "$local_md5" = "$remote_md5" ]; then
        echo "-- 跳过（两端一致）$rel"
        SKIPPED=$((SKIPPED+1)); continue
    fi

    lines=$(diff "$base" "$f" | grep -c '^[<>]' || true)
    echo "== 待上线 $rel（差异 $lines 行）"
    diff -u "$base" "$f" | head -20 || true

    if [ "$DRY" = "1" ]; then
        echo "   [dry-run] 未上传"
        CHANGED=$((CHANGED+1)); continue
    fi

    # 备份 → 传 /tmp → cp 覆盖（避免 scp 直写半截文件）→ 校验
    ssh "${SSH_OPTS[@]}" "$HOST" "cd $(dirname "$rpath") && cp -a $(basename "$rpath") $(basename "$rpath").bak.$TS" \
        || { echo "!! 备份失败，已中止（不覆盖）" >&2; FAILED=$((FAILED+1)); continue; }

    scp -q "${SSH_OPTS[@]}" "$f" "$HOST:/tmp/deploy_$(basename "$rpath").$$" \
        || { echo "!! 上传失败" >&2; FAILED=$((FAILED+1)); continue; }

    ssh "${SSH_OPTS[@]}" "$HOST" "cp /tmp/deploy_$(basename "$rpath").$$ '$rpath' && chmod 644 '$rpath' && rm -f /tmp/deploy_$(basename "$rpath").$$" \
        || { echo "!! 覆盖失败" >&2; FAILED=$((FAILED+1)); continue; }

    after=$(ssh "${SSH_OPTS[@]}" "$HOST" "md5sum '$rpath'" | awk '{print $1}')
    if [ "$after" = "$local_md5" ]; then
        echo "   ok  $rel  （备份 $(basename "$rpath").bak.$TS）"
        CHANGED=$((CHANGED+1))
    else
        echo "!! 校验不一致：本地 $local_md5 / 线上 $after" >&2
        FAILED=$((FAILED+1))
    fi
done

echo "----------------------------------------"
echo "改动 $CHANGED | 跳过 $SKIPPED | 失败 $FAILED"
if [ "$CHANGED" -gt 0 ] && [ "$DRY" = "0" ]; then
    echo "提示：静态文件已生效，无需重启；若改了 JS/CSS，记得同步 bump index.html 里的 ?v=。"
    echo "回滚：ssh -i $KEY $HOST \"cd $RDIR && cp -a <文件>.bak.$TS <文件>\""
fi
[ "$FAILED" -eq 0 ]
