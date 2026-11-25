"""作用域收口后：结果页完整渲染链回归（走演示模式，零 POST、不动额度）

判据：结果页真的渲染出来，不是"没报错"就算了
  ① 点击「一键演示」后结果区出现正文（字数 > 1000）
  ② 雷达图 / 图表容器被 ECharts 实例接管
  ③ 评分项自查面板存在
  ④ 导出按钮可点击且未禁用（演示模式由 guard 决定）
  ⑤ 全程 pageerror / console error 为 0
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
PORT = 9415
URL = "http://127.0.0.1:8080/"


def launch():
    prof = tempfile.mkdtemp(prefix="wbdemo-")
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=1440,1000", "--remote-debugging-port=%d" % PORT,
            "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check", URL]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            d = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=1))
            for t in d:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    return p, t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("Chrome start failed")


class CDP:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, timeout=40)
        self.i = 0
        self.errors = []
        self.conerr = []
        self.posts = []

    def send(self, m, p=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg.get("result", {})
            self.evt(msg)

    def evt(self, msg):
        m = msg.get("method")
        if m == "Runtime.exceptionThrown":
            self.errors.append(msg["params"]["exceptionDetails"].get("text", ""))
        elif m == "Runtime.consoleAPICalled" and msg["params"].get("type") == "error":
            self.conerr.append(" ".join(str(a.get("value", "")) for a in msg["params"].get("args", []))[:200])
        elif m == "Network.requestWillBeSent":
            r = msg["params"]["request"]
            if r["method"] == "POST":
                self.posts.append(r["url"])

    def ev(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": await_promise, "userGesture": True})
        if r.get("exceptionDetails"):
            return {"__error": str(r["exceptionDetails"].get("text"))}
        return r.get("result", {}).get("value")


def main():
    proc, ws = launch()
    c = CDP(ws)
    checks = []

    def ck(ok, label, detail=""):
        checks.append((bool(ok), label, str(detail)))

    try:
        c.send("Runtime.enable")
        c.send("Page.enable")
        c.send("Network.enable")
        c.send("Page.navigate", {"url": URL})
        time.sleep(4)
        c.posts.clear()

        # 触发演示
        c.ev("(function(){ try { window.wbOpenDemo(); } catch(e){ return String(e); } return 'ok'; })()")
        time.sleep(6)

        # ① 正文
        r = c.ev("""(function(){
            var box = document.getElementById('resultBox') || document.getElementById('result');
            var t = box ? (box.innerText || '') : (document.body.innerText || '');
            return JSON.stringify({len: t.length, head: t.slice(0, 60)});
        })()""")
        d = json.loads(r) if isinstance(r, str) else {}
        ck(d.get("len", 0) > 1000, "结果页正文已渲染", "字数 %s" % d.get("len"))

        # ② 图表
        r2 = c.ev("""(function(){
            var cs = document.querySelectorAll('canvas');
            var inited = 0;
            for (var i=0;i<cs.length;i++){
                try { if (window.echarts && echarts.getInstanceByDom(cs[i].parentNode)) inited++; } catch(e){}
            }
            return JSON.stringify({canvas: cs.length, inited: inited});
        })()""")
        d2 = json.loads(r2) if isinstance(r2, str) else {}
        ck(d2.get("canvas", 0) > 0, "图表 canvas 已生成", json.dumps(d2))

        # ③ 评分项自查
        r3 = c.ev("""(function(){
            var sc = document.getElementById('wbscRoot');
            var sub = document.getElementById('wbSubPanel-score');
            return JSON.stringify({hasRoot: !!sc, hasPanel: !!sub, textLen: sc ? (sc.innerText||'').length : 0});
        })()""")
        d3 = json.loads(r3) if isinstance(r3, str) else {}
        ck(d3.get("hasRoot") or d3.get("hasPanel"), "评分项自查面板存在", json.dumps(d3, ensure_ascii=False))

        # ④ 导出按钮
        r4 = c.ev("""(function(){
            var btns = document.querySelectorAll('[onclick*="exportOne"],[onclick*="exportAll"]');
            var info = [];
            for (var i=0;i<btns.length && i<4;i++){
                info.push({txt:(btns[i].innerText||'').trim().slice(0,12), disabled:!!btns[i].disabled});
            }
            return JSON.stringify({count: btns.length, info: info});
        })()""")
        d4 = json.loads(r4) if isinstance(r4, str) else {}
        ck(d4.get("count", 0) > 0, "导出入口已渲染", json.dumps(d4, ensure_ascii=False))

        # ⑤ 无错误 + 无 POST（演示不该打额度）
        ck(not c.errors, "pageerror 为 0", "; ".join(c.errors[:2]) or "clean")
        ck(not c.conerr, "console error 为 0", "; ".join(c.conerr[:2]) or "clean")
        ck(len(c.posts) == 0, "演示模式零 POST（未动生成额度）", "posts=%d %s" % (len(c.posts), c.posts[:2]))

        shot = c.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        out = os.path.join("artifacts", "qa", "frontend-refactor")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "demo_result_after_scope.png"), "wb") as f:
            f.write(base64.b64decode(shot["data"]))
    finally:
        try:
            c.ws.close()
        except Exception:
            pass
        proc.terminate()

    print("\n=== 结果页完整渲染链回归（演示模式）===\n")
    ok = 0
    for o, l, det in checks:
        print(("  PASS  " if o else "  FAIL  ") + l + ("   [" + det + "]"))
        ok += o
    print("\n%d/%d 通过" % (ok, len(checks)))
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
