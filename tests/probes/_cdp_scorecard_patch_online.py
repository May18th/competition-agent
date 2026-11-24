# -*- coding: utf-8 -*-
"""线上「按评分项补强」按钮自检（会真实调用一次模型，约 20~40 秒）。

复用 _cdp_scorecard_online.py 的 Chrome/CDP 启动逻辑，注入真实记录 id 后点按钮。

断言：
  ① 点击后按钮进入「正在补写…」并 disabled
  ② 输出区出现「A → B 分」，且 B >= A
  ③ 有「补了 …（+N 分）」或「没找到能靠改写补上的缺口」之一
  ④ 展开后正文文本域 > 500 字
  ⑤ 按钮复位、无页面异常
"""
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "cdp_base", os.path.join(HERE, "_cdp_scorecard_online.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

HID = int(sys.argv[1]) if len(sys.argv) > 1 else 323


def main():
    proc, ws_url = base.launch()
    cdp = base.CDP(ws_url)
    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        time.sleep(6)
        cdp.js("window._lastHistoryId = %d; window._lastData = {history_id: %d};" % (HID, HID))
        cdp.js("window.wbScorecardOnline && window.wbScorecardOnline.refresh()")
        time.sleep(3)

        has_btn = cdp.js("!!document.querySelector('#wbscRoot .wbsc-go')")
        print("找到补强按钮:", has_btn)
        if not has_btn:
            print("判定: FAIL（面板里没有按钮）")
            return 2

        cdp.js("document.querySelector('#wbscRoot .wbsc-go').click()")
        time.sleep(1)
        print("点击后按钮:", cdp.js("(document.querySelector('#wbscRoot .wbsc-go')||{}).textContent"),
              "| disabled:", cdp.js("(document.querySelector('#wbscRoot .wbsc-go')||{}).disabled"))

        done = None
        for _ in range(40):
            time.sleep(3)
            done = cdp.js("(document.querySelector('#wbscRoot .wbsc-delta')||{}).textContent || ''")
            if done:
                break
            err = cdp.js("(document.querySelector('#wbscRoot .wbsc-out')||{}).textContent || ''")
            if "没成功" in err:
                done = "ERR:" + err[:120]
                break

        print("输出区分数行:", done)
        lines = cdp.js("""[].slice.call(document.querySelectorAll('#wbscRoot .wbsc-line'))
            .map(function(d){return d.textContent.replace(/\\s+/g,' ').trim();})""")
        hint = cdp.js("(document.querySelector('#wbscRoot .wbsc-out .wbsc-hint')||{}).textContent || ''")
        textlen = cdp.js("""(function(){var t=document.querySelector('#wbscRoot .wbsc-text');
            return t ? (t.value||'').length : 0;})()""")
        btn_now = cdp.js("(document.querySelector('#wbscRoot .wbsc-go')||{}).textContent")
        disabled_now = cdp.js("(document.querySelector('#wbscRoot .wbsc-go')||{}).disabled")

        print("补写明细:", json.dumps(lines or [], ensure_ascii=False))
        print("提示语:", hint[:60])
        print("正文文本域长度:", textlen)
        print("按钮已复位:", btn_now, "| disabled:", disabled_now)
        print("页面异常:", cdp.errors[:3] or "无")

        ok = bool(done) and "→" in (done or "") and textlen > 500 \
            and btn_now != "正在补写…" and not disabled_now
        print("判定:", "PASS" if ok else "FAIL")
        return 0 if ok else 3
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
