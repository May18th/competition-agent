# -*- coding: utf-8 -*-
"""本地首页「加载卡死」二分定位。

现象：frontend/index.html 在 headless 里永远加载不完（截图/dump 全 timeout），
而线上那套能跑。用删减资源的方式二分：每次只保留一部分 <link>/<script>，
渲染成功即「这批不是元凶」。

用法：python tests/probes/_bisect_page.py <port> [kinds]
  kinds: css / js / both（默认 both）
每次会改写 TESTDIR/index.html，跑完自动还原。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHROME = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
TESTDIR = os.path.join(tempfile.gettempdir(), "localtest")
SRC = os.path.join(TESTDIR, "index.html")
BAK = os.path.join(TESTDIR, "index.orig.html")
PORT = sys.argv[1] if len(sys.argv) > 1 else "8095"

LINK_RE = re.compile(r'^[ \t]*<link[^>]+stylesheet[^>]*>[ \t]*$', re.M)
SCRIPT_RE = re.compile(r'^[ \t]*<script[^>]+src=[^>]*>[ \t]*</script>[ \t]*$', re.M)


def load():
    with open(BAK, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")   # 统一 LF，免得行尾混进比对


def keep(html, links, scripts, keep_links, keep_scripts):
    """把不在保留名单里的 <link>/<script> 整行删掉。"""
    out = []
    for line in html.split("\n"):
        if LINK_RE.match(line):
            idx = links.index(line)
            if idx not in keep_links:
                continue
        elif SCRIPT_RE.match(line):
            idx = scripts.index(line)
            if idx not in keep_scripts:
                continue
        out.append(line)
    return "\n".join(out)


def render_ok(timeout=20):
    out = os.path.join(tempfile.gettempdir(), "bisect_shot.png")
    if os.path.exists(out):
        os.remove(out)
    try:
        subprocess.run([
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--incognito",
            "--hide-scrollbars", "--window-size=1000,800", "--virtual-time-budget=3000",
            "--screenshot=" + out, "http://127.0.0.1:%s/" % PORT,
        ], timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False
    return os.path.exists(out) and os.path.getsize(out) > 20000


def main():
    if not os.path.exists(BAK):
        shutil.copy2(SRC, BAK)
    base = load()
    links = LINK_RE.findall(base)
    scripts = SCRIPT_RE.findall(base)

    def test(name, keep_l, keep_s):
        with open(SRC, "w", encoding="utf-8", newline="") as f:
            f.write(keep(base, links, scripts, keep_l, keep_s))
        ok = render_ok()
        print("%-46s %s" % (name, "渲染成功" if ok else "仍卡死"))
        return ok

    print("共 %d 个样式表 / %d 个脚本" % (len(links), len(scripts)))
    if not test("① 全删（只剩 HTML）", set(), set()):
        print("→ 连纯 HTML 都卡，问题不在资源，可能是 CSS 内联或 HTML 结构")
        return
    if not test("② 只留全部样式表，删光脚本", set(range(len(links))), set()):
        print("→ 元凶在样式表里")
        return
    if not test("③ 只留全部脚本，删光样式表", set(), set(range(len(scripts)))):
        print("→ 元凶在脚本里")
        return
    print("→ 单独留 css 或单独留 js 都能渲染，说明是两者的组合（少见），需人工看")


if __name__ == "__main__":
    main()
