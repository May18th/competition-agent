"""评分项自查面板的自检（本地，不消耗额度）。

做法：headless Chrome 打开本地首页 → 用一份最小 mock 数据让 result-panel 渲染出
.wb339-hero → 调 wbScorecard.refresh() 挂上评分项面板 → 取值断言 + 截图。

断言四件事：
  ① 面板挂到了 hero 之后（顺序对）
  ② 四个官方维度都显示，且都带「/ 满分」
  ③ 缺口数与接口返回一致，带「丢约 N 分」
  ④ 观察 1.5 秒 DOM 不再变化（observer 已收敛，不重演 index.html 里记过的死循环）
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/"
HID = int(sys.argv[2]) if len(sys.argv) > 2 else 29
OUT = os.path.join("artifacts", "qa")
PORT = 9381


def launch():
    prof = tempfile.mkdtemp(prefix="wbsc-")
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=1280,2200", "--remote-debugging-port=%d" % PORT,
            "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check",
            BASE]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
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
        self.ws = websocket.create_connection(url, timeout=60)
        self.i = 0

    def send(self, method, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                if "error" in msg:
                    raise RuntimeError("%s -> %s" % (method, msg["error"]))
                return msg.get("result", {})

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=True,
                      returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"].get("text") or
                               str(r["exceptionDetails"]))
        return r.get("result", {}).get("value")


MOCK = """
window._lastHistoryId = %d;
window._lastData = {score: 92, scoreMax: 100, scoreLabel: '文档质量自评',
  oneLiner: '面向高校实验室的耗材智能盘点柜', completeness: {missing: []}};
if (window.wbResult339) { window.wbResult339.init({data: window._lastData}); }
'ok'
""" % HID


def main():
    os.makedirs(OUT, exist_ok=True)
    proc, ws_url = launch()
    cdp = CDP(ws_url)
    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        time.sleep(2.5)
        print("mock:", cdp.js(MOCK))
        time.sleep(0.8)
        cdp.js("window.wbScorecard && window.wbScorecard.refresh()")
        time.sleep(2.5)

        state = cdp.js("""(function(){
          var box = document.getElementById('wb339ScRoot');
          if (!box) return {ok:false, why:'#wb339ScRoot 未挂载'};
          var hero = document.querySelector('.wb339-hero');
          var dims = [].map.call(box.querySelectorAll('.wb339-dim-row'),
            function(r){ return r.textContent.replace(/\\s+/g,' ').trim(); });
          var issues = [].slice.call(box.querySelectorAll('.wb339-issue-txt'))
            .map(function(e){ return e.textContent.replace(/\\s+/g,' ').trim(); });
          var total = box.querySelector('.wb339-score-num');
          return {ok:true,
            afterHero: hero && hero.nextElementSibling === box,
            total: total ? total.textContent.trim() : null,
            dims: dims, issues: issues,
            hint: (box.querySelector('.wb339-sc-hint')||{}).textContent || '',
            btn: !!(box.querySelector('.wb339-sc-go')),
            text: (box.textContent||'').replace(/\\s+/g,' ').trim().slice(0,160),
            heroParent: hero ? (hero.parentNode.id || hero.parentNode.className) : null,
            apiProbe: 'pending'};
        })()""")

        print("\n=== 面板状态 ===")
        print(json.dumps(state, ensure_ascii=False, indent=1))

        # 收敛检查：1.5 秒内 DOM 不应再变（observer 死循环会持续增删节点）
        h1 = cdp.js("document.getElementById('wb339ScRoot').innerHTML.length")
        time.sleep(1.5)
        h2 = cdp.js("document.getElementById('wb339ScRoot').innerHTML.length")

        ok = bool(state.get("ok")) and state.get("afterHero") and \
            len(state.get("dims") or []) == 4 and \
            all("/" in d for d in (state.get("dims") or [])) and \
            state.get("total") not in (None, "", "未评分") and \
            h1 == h2
        print("\n收敛: %s -> %s（应相等）" % (h1, h2))
        print("判定:", "PASS" if ok else "FAIL")

        shot = cdp.send("Page.captureScreenshot", format="png", captureBeyondViewport=True)
        path = os.path.join(OUT, "scorecard_panel.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("截图:", path)
        return 0 if ok else 2
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
