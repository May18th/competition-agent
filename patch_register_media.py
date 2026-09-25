# -*- coding: utf-8 -*-
"""
patch_register_media.py —— 把 media_routes 蓝图注册进 app.py（幂等，可重复跑）

只做一件事：在 `app = Flask(__name__)` 后面插入 5 行注册代码。
不碰 app.py 的任何既有路由，避免和 Codex 的改动冲突。

跑完会打印命中次数，别信 ✅，看数字。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(BASE, "app.py")

ANCHOR = "app = Flask(__name__)"

INSERT = ANCHOR + """

# ===== 媒体模块（表格 / 图表 / PPT）=====
# 由 media_routes.py 提供，WorkBuddy 注册。
# ⚠️ 改 app.py 时请不要删这段，删了前端的图表和 PPT 下载会 404。
try:
    from media_routes import media_bp
    app.register_blueprint(media_bp)
    print("✅ 媒体模块已注册：/api/media/*")
except Exception as _media_err:
    print("⚠️ 媒体模块注册失败：", _media_err)
# ===== 媒体模块结束 =====
"""

MARK = "from media_routes import media_bp"


def main():
    if not os.path.isfile(TARGET):
        print("❌ 找不到 app.py")
        return 1

    with io.open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    before_len = len(src)
    print(f"app.py 原始长度：{before_len}")

    if MARK in src:
        print("✅ 已经注册过了，跳过（命中 0 处替换）")
        return 0

    anchor_count = src.count(ANCHOR)
    print(f"锚点 `app = Flask(__name__)` 出现次数：{anchor_count}")
    if anchor_count != 1:
        print("❌ 锚点数量不是 1，拒绝自动修改，请人工处理")
        return 1

    src = src.replace(ANCHOR, INSERT, 1)

    # 备份
    bak = TARGET + ".bak.media"
    try:
        with io.open(bak, "w", encoding="utf-8") as f:
            f.write(open(TARGET, encoding="utf-8").read())
        print(f"已备份：{os.path.basename(bak)}")
    except Exception as e:
        print("⚠️ 备份失败：", e)

    with io.open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)

    # 核验
    with io.open(TARGET, "r", encoding="utf-8") as f:
        new = f.read()
    print(f"替换后长度：{len(new)}（+{len(new) - before_len}）")
    print(f"核验命中：media_bp 出现 {new.count(MARK)} 次（应为 1）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
