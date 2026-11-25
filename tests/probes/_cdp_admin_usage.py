# -*- coding: utf-8 -*-
"""线上看板实测：带管理会话 cookie 打开 /admin/llm-usage，校验「单次生成成本」区块。

只读页面，不写任何数据。
"""
import json
import sys

from playwright.sync_api import sync_playwright

COOKIE = sys.argv[1]
BASE = "https://8.149.236.90"
OUT = "D:/competition-agent/artifacts/qa/admin_usage_pergen.png"

errors = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", args=["--ignore-certificate-errors"])
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 1400})
    ctx.add_cookies([{
        "name": "admin_session",
        "value": COOKIE,
        "domain": "8.149.236.90",
        "path": "/",
        "httpOnly": True,
        "secure": True,
        "sameSite": "Strict",
    }])
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(BASE + "/admin/llm-usage", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(1500)

    state = page.inner_text("#state")
    print("state:", state)

    metrics = page.eval_on_selector_all(
        "#genmetrics .metric",
        "els => els.map(e => [e.querySelector('.label').textContent, e.querySelector('.value').textContent])")
    print("指标卡 %d 个:" % len(metrics))
    for k, v in metrics:
        print("   %s = %s" % (k, v))

    modes = page.eval_on_selector_all(
        "#genmodes table tr",
        "els => els.map(tr => Array.from(tr.children).map(td => td.textContent))")
    print("按版本分桶 %d 行:" % len(modes))
    for row in modes:
        print("   ", row)

    rows = page.eval_on_selector_all(
        "#gentasks table tbody tr",
        "els => els.map(tr => Array.from(tr.children).map(td => td.textContent))")
    print("明细 %d 行" % len(rows))
    for row in rows[:3]:
        print("   ", row)

    note = page.inner_text("#gennote")
    print("注：", note)

    page.screenshot(path=OUT, full_page=True)
    print("截图:", OUT)

    # 原有区块仍在
    for el in ("#calls", "#total", "#daily", "#sections", "#models", "#tasks", "#users"):
        assert page.query_selector(el) is not None, "缺失元素 " + el
    print("原有区块齐全")

    b.close()

if errors:
    print("JS 报错:", errors)
    sys.exit(1)
print("ALL PASS")
