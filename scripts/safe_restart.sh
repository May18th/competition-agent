#!/usr/bin/env bash
# 安全重启 comp-agent：等在跑的生成任务跑完再 systemctl restart。
#
# 背景（2026-09-27 实锤）：tasks/线程全在进程内存里，SIGTERM 后 Python 解释器
# 关闭会让 langgraph 线程池报 "cannot schedule new futures after interpreter
# shutdown"，在跑的深度版（4~8 分钟）被拦腰杀掉，用户看到「任务已失效」假失败，
# 数据库无记录。一天内三次重启连杀三个任务后加的这个闸。
#
# 用法：bash /opt/comp-agent/scripts/safe_restart.sh [最长等待秒数，默认 600]
# 原理：app.py 在每次生成计数变化时把在跑数量写到 /tmp/comp_agent_gens，
#       本脚本轮询它，归零（或超时）才重启。任何人都不要再裸 systemctl restart。
MAX_WAIT=${1:-600}
# 421 轮孪生站独立化：marker 随工作目录（生产 /opt/comp-agent、staging /opt/comp-agent-staging 各自独立），
# 不再用 /tmp/comp_agent_gens（否则两边互相覆盖计数）。
MARK="$(pwd)/.comp_agent_gens"
STEP=5
waited=0
while [ "$waited" -lt "$MAX_WAIT" ]; do
    n=$(cat "$MARK" 2>/dev/null || echo 0)
    n=${n:-0}
    if [ "$n" -le 0 ]; then
        break
    fi
    echo "⏳ 在跑生成任务 ${n} 个，等待中（${waited}s / 上限 ${MAX_WAIT}s）..."
    sleep "$STEP"
    waited=$((waited + STEP))
done
n=$(cat "$MARK" 2>/dev/null || echo 0)
n=${n:-0}
if [ "$n" -gt 0 ]; then
    echo "⚠ 仍有 ${n} 个任务在跑，已到等待上限，强制重启（这些任务会中断）"
fi
systemctl restart comp-agent
sleep 2
echo "重启完成：$(systemctl is-active comp-agent)"
