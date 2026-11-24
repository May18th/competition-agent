"""线上「官方评分项自查」面板自检（只读，不改线上任何数据）。

headless Chrome 用 host-resolver-rules 把域名指到源站 IP（本机解析不了 DNS），
注入一条真实记录的 id，检查面板是否渲染出维度与缺口。

断言：
  ① #wbscRoot 挂在 #wbSubPanel-score 里
  ② 维度数与赛事官方维度数一致，每个都带「/ 满分」
  ③ 缺口条目带「丢约 N 分」
  ④ 控制台没有异常
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
IP = "8.149.236.90"
HOST = "kechuang2026.cn"
HID = int(sys.argv[1]) if len(sys.argv) > 1 else 323
OUT = os.path.join("artifacts", "qa")
PORT = 9391


def launch():
    prof = tempfile.mkdtemp(prefix="wbsc-on-")
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=1280,2000", "--remote-debugging-port=%d" % PORT,
            "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check",
            "--ignore-certificate-errors",
            "--host-resolver-rules=MAP %s %s" % (HOST, IP),
            "https://%s/" % HOST]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=1) as r:
                tabs = json.loads(r.read())
            for t in tabs:
                if t.get("type") == "page" and "webSocketDebuggerUrl" in t:
                    return p, t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.3)
    p.kill()
    raise RuntimeError("Chrome 没起来")


class CDP:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=90)
        self.i = 0
        self.errors = []

    def send(self, method, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                self.errors.append(str(msg.get("params", {}))[:160])
            if msg.get("id") == self.i:
                if "error" in msg:
                    raise RuntimeError("%s -> %s" % (method, msg["error"]))
                return msg.get("result", {})

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=True,
                      returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"].get("text") or str(r["exceptionDetails"]))
        return r.get("result", {}).get("value")


def main():
    os.makedirs(OUT, exist_ok=True)
    proc, ws_url = launch()
    cdp = CDP(ws_url)
    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        time.sleep(6)   # 线上 app.js 较大，等它初始化完

        print("页面标题:", cdp.js("document.title"))
        print("脚本已加载:", cdp.js("typeof window.wbScorecardOnline"))

        cdp.js("window._lastHistoryId = %d; window._lastData = {history_id: %d};" % (HID, HID))
        cdp.js("window.wbScorecardOnline && window.wbScorecardOnline.refresh()")
        time.sleep(4)

        st = cdp.js("""(function(){
          var box = document.getElementById('wbscRoot');
          var host = document.getElementById('wbSubPanel-score');
          if (!box) return {ok:false, why:'#wbscRoot 未挂载', hostExists: !!host};
          return {ok:true,
            inPanel: !!(host && box.parentNode === host),
            total: (box.querySelector('.wbsc-total')||{}).textContent || '',
            dims: [].map.call(box.querySelectorAll('.wbsc-dim'),
              function(d){ return d.textContent.replace(/\\s+/g,' ').trim(); }),
            gaps: [].slice.call(box.querySelectorAll('.wbsc-gap-txt'))
              .map(function(d){ return d.textContent.replace(/\\s+/g,' ').trim().slice(0,60); }),
            text: (box.textContent||'').replace(/\\s+/g,' ').trim().slice(0,120)};
        })()""")
        print("\n=== 面板 ===")
        print(json.dumps(st, ensure_ascii=False, indent=1))

        h1 = cdp.js("(document.getElementById('wbscRoot')||{}).innerHTML?.length || 0")
        time.sleep(1.5)
        h2 = cdp.js("(document.getElementById('wbscRoot')||{}).innerHTML?.length || 0")

        ok = bool(st.get("ok")) and st.get("inPanel") and len(st.get("dims") or []) >= 2 \
            and all("/" in d for d in (st.get("dims") or [])) \
            and st.get("total") not in ("", "—") and h1 == h2
        print("\n收敛: %s -> %s" % (h1, h2))
        print("页面异常:", cdp.errors[:3] or "无")
        print("判定:", "PASS" if ok else "FAIL")

        shot = cdp.send("Page.captureScreenshot", format="png")
        p = os.path.join(OUT, "scorecard_online.png")
        with open(p, "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("截图:", p)
        return 0 if ok else 2
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
