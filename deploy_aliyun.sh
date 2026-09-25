#!/usr/bin/env bash
# 阿里云轻量/ESC 一键部署脚本（Ubuntu / Debian / Alibaba Linux / CentOS 通用）
# 用法：登录阿里云控制台 → 远程连接（Workbench）→ 粘贴整段执行
# 注意：安全组放行端口要在阿里云控制台手动做，脚本管不到

set -e

APP_DIR=/opt/comp-agent
REPO=https://github.com/May18th/competition-agent.git
PORT=8080
PY=python3

need_cmd() { command -v "$1" >/dev/null 2>&1; }

echo "===== [1/7] 系统准备：依赖 + 中文字体 + swap ====="
if need_cmd apt-get; then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y git "$PY" "$PY-venv" "$PY-pip" \
        fonts-noto-cjk curl
elif need_cmd dnf; then
    dnf install -y git python3 python3-pip curl
    dnf install -y google-noto-sans-cjk-fonts 2>/dev/null \
      || dnf install -y wqy-zenhei-fonts 2>/dev/null \
      || echo "!!! 中文字体没装上，图表中文会变方框，请手动装 fonts"
elif need_cmd yum; then
    yum install -y git python3 python3-pip curl
    yum install -y google-noto-sans-cjk-fonts 2>/dev/null \
      || yum install -y wqy-zenhei-fonts 2>/dev/null \
      || echo "!!! 中文字体没装上，图表中文会变方框，请手动装 fonts"
fi

# 2G 内存的小机器必配 swap，否则深度模式（langchain + matplotlib）容易 OOM 被杀
if [ "$(awk '/SwapTotal/{print int($2/1024/1024)}' /proc/meminfo)" -lt 1 ]; then
    echo ">>> 内存 swap 不足，创建 2G swapfile"
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "===== [2/7] 拉代码 ====="
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR" && git pull
else
    # 私有仓库改这里：REPO=https://<你的token>@github.com/May18th/competition-agent.git
    git clone "$REPO" "$APP_DIR" \
      || git clone "https://ghfast.top/$REPO" "$APP_DIR" \
      || git clone "https://gh-proxy.com/$REPO" "$APP_DIR" \
      || { echo "克隆失败：仓库若是私有，请换成带 token 的地址"; exit 1; }
fi
cd "$APP_DIR"

echo "===== [3/7] 建虚拟环境 + 装依赖（走清华源，国内快）====="
if [ ! -d .venv ]; then "$PY" -m venv .venv; fi
. .venv/bin/activate
python -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo "===== [4/7] 配置环境变量（DeepSeek Key）====="
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" <<EOF
DEEPSEEK_API_KEY=sk-在这里填你的key
PORT=$PORT
EOF
    chmod 600 "$APP_DIR/.env"
    echo ">>> 已生成 $APP_DIR/.env，请把 DEEPSEEK_API_KEY 换成真 key，然后："
    echo ">>>   systemctl restart comp-agent"
fi

echo "===== [5/7] 写 systemd 服务（开机自启 + 崩了自动拉起）====="
cat > /etc/systemd/system/comp-agent.service <<EOF
[Unit]
Description=科创赛事多智能体协同创作助手
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 600
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "===== [6/7] 起服务 ====="
systemctl daemon-reload
systemctl enable comp-agent
systemctl restart comp-agent
sleep 4
systemctl status comp-agent --no-pager | head -12 || true

echo "===== [7/7] 放行端口（系统防火墙；阿里云安全组请自行在控制台放行 $PORT）====="
need_cmd ufw && ufw allow "$PORT"/tcp || true
if need_cmd firewall-cmd; then
    firewall-cmd --permanent --add-port="$PORT"/tcp >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1 || true
fi

echo ""
echo "===== 自检 ====="
curl -s -m 8 "http://127.0.0.1:$PORT/api/health" || echo "还没起来，用 journalctl -u comp-agent -f 看日志"
