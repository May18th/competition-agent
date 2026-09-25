# -*- coding: utf-8 -*-
"""防回归校验：app.py 的启动块不能挡住后面的路由。

正确姿势（二选一，推荐第一种）：
  1) app.py 里【不写】启动块，本地用 run.py，云端用 gunicorn wsgi:app；
  2) 非写不可时，启动块必须放在文件【最末尾】、所有 @app.route 之后。

用法：
    python _check_startup.py
退出码 0=通过，1=启动块位置错误。
"""
import re
import sys


def main():
    with open("app.py", encoding="utf-8") as f:
        lines = f.read().splitlines()

    route_lines = [i for i, l in enumerate(lines, 1)
                   if re.match(r"\s*@app\.route", l)]
    main_lines = [i for i, l in enumerate(lines, 1)
                  if re.match(r"if\s+__name__\s*==\s*['\"]__main__['\"]", l)]
    last_route = max(route_lines) if route_lines else 0

    if not main_lines:
        print("PASS：app.py 没有启动块（推荐；run.py / wsgi.py 是入口）")
        return 0

    bad = [i for i in main_lines if i < last_route]
    if bad:
        print(f"FAIL：启动块在第 {bad} 行，但最后一个路由在第 {last_route} 行。")
        print("      启动块会堵死后面的路由（本地直跑 404），请删除或移到文件末尾。")
        return 1
    print(f"PASS：启动块在第 {main_lines[-1]} 行，位于所有路由之后。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
