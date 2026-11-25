# -*- coding: utf-8 -*-
"""后台四个页面改造后实测：截图 + 提取可见文案，确认黑话已清干净。

只读，不写数据。
"""
import re
import sys

from playwright.sync_api import sync_playwright

COOKIE = sys.argv[1]
BASE = "https://8.149.236.90"
OUT = "D:/competition-agent/artifacts/qa/"

# 仍然出现就说明没翻译干净
JARGON = ["记录口径", "工单", "范式", "蒸馏", "数据洞察", "赛事资料缺口",
          "反馈优先级", "评分弱项", "失败模式", "档位", "p90", "口径",
          "样本量", "脱敏", "可交付", "软警告", "硬拦截", "同质化"]

PAGES = [("/admin", "admin_overview"), ("/admin/panel", "admin_panel"),
         ("/monitor", "admin_monitor"), ("/admin/llm-usage", "admin_usage")]

errors = []
hits_total = {}

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", args=["--ignore-certificate-errors"])
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 1300})
    ctx.add_cookies([{"name": "admin_session", "value": COOKIE, "domain": "8.149.236.90",
                      "path": "/", "httpOnly": True, "secure": True, "sameSite": "Strict"}])
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    for path, name in PAGES:
        page.goto(BASE + path, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(1200)
        body = page.inner_text("body")
        hits = [w for w in JARGON if w in body]
        hits_total[path] = hits
        page.screenshot(path=OUT + name + "_plain.png", full_page=True)
        print("%-18s 字符 %5d  黑话残留: %s" % (path, len(body), hits or "无"))

    b.close()

print()
if errors:
    print("JS 报错:", errors[:5])
    sys.exit(1)
bad = {k: v for k, v in hits_total.items() if v}
if bad:
    print("仍有黑话:", bad)
    sys.exit(2)
print("ALL PASS · 四页无黑话无报错")
