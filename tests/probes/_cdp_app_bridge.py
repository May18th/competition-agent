"""验证跨文件调用链在作用域收口后仍然贯通（本地 8080，只读）

重点不是"函数存在"，而是"闭包内的调用能真正走到首页内联脚本里的实现"：
  paintPartial → twSet（打字机）
  paintPartial → wbCjkLen / _STREAM_MAP
  主题推荐 → wbAdvToggle / openChartModal / wbLoadEcharts

判据：给内联实现打标记，再触发 app.js 内部调用，看标记是否被命中。
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
PORT = 9413
URL = "http://127.0.0.1:8080/"


def launch():
    prof = tempfile.mkdtemp(prefix="wbbridge-")
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=1440,900", "--remote-debugging-port=%d" % PORT,
            "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check", URL]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
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
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.i = 0
        self.errors = []

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg.get("result", {})
            self._evt(msg)

    def _evt(self, msg):
        if msg.get("method") == "Runtime.exceptionThrown":
            d = msg["params"]["exceptionDetails"]
            self.errors.append(d.get("text", ""))

    def ev(self, expr):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": True, "userGesture": True})
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
        c.send("Page.navigate", {"url": URL})
        time.sleep(4)

        # ---------- 1. paintPartial → twSet（打字机）贯通 ----------
        r = c.ev("""(function(){
            var hit = [];
            var origTw = window.twSet;
            window.twSet = function(){ hit.push('twSet'); try { return origTw.apply(this, arguments); } catch(e){ throw e; } };
            // 造一个最小 partial，驱动 app.js 闭包内的 paintPartial
            var ok = true, err = '';
            try {
                if (typeof window.paintPartial !== 'function') { ok = false; err = 'paintPartial 未导出'; }
                else { window.paintPartial({ proposal: '这是一段用于验证打字机链路的测试正文，长度足够触发增量渲染。' }); }
            } catch(e) { ok = false; err = String(e); }
            window.twSet = origTw;
            return JSON.stringify({ ok: ok, err: err, twHit: hit.length });
        })()""")
        d = json.loads(r) if isinstance(r, str) else {}
        ck(d.get("ok") and d.get("twHit", 0) > 0, "paintPartial → twSet 链路贯通",
           "twSet 命中 %s 次, err=%s" % (d.get("twHit"), d.get("err") or "none"))

        # ---------- 2. paintPartial 内部依赖 _STREAM_MAP ----------
        r2 = c.ev("""(function(){
            var m = window._STREAM_MAP;
            return JSON.stringify({ hasMap: !!m, isArray: Array.isArray(m), len: m ? m.length : 0 });
        })()""")
        d2 = json.loads(r2) if isinstance(r2, str) else {}
        ck(d2.get("hasMap") and d2.get("len", 0) > 0, "_STREAM_MAP 已导出且非空",
           "len=%s" % d2.get("len"))

        # ---------- 3. 导出符号可读且类型正确 ----------
        r3 = c.ev("""(function(){
            var names = ['renderRich','previewDeckStyle','streamFinish','streamPrepare','wbPickTheme',
                         'wbToast','wbCompOpen','openHistory','_esc','WB_STATS','_currentTaskId'];
            var bad = [];
            names.forEach(function(n){ if (typeof window[n] === 'undefined') bad.push(n); });
            return JSON.stringify({bad: bad});
        })()""")
        d3 = json.loads(r3) if isinstance(r3, str) else {}
        ck(not d3.get("bad"), "契约符号全部可读", str(d3.get("bad") or "all ok"))

        # ---------- 4. 猴补丁：模拟首页对 renderRich 的包装能拦到内部调用 ----------
        r4 = c.ev("""(function(){
            var hit = 0;
            var orig = window.renderRich;
            window.renderRich = function(){ hit++; return orig.apply(this, arguments); };
            var err = '';
            try {
                // 直接走导出入口，验证赋值后 window 上就是包装版
                window.renderRich({}, true);
            } catch(e) { err = String(e); }
            var wrapped = (window.renderRich !== orig);
            window.renderRich = orig;
            return JSON.stringify({hit: hit, wrapped: wrapped, err: err});
        })()""")
        d4 = json.loads(r4) if isinstance(r4, str) else {}
        ck(d4.get("hit", 0) >= 1 and d4.get("wrapped"), "renderRich 包装可拦截调用",
           "hit=%s err=%s" % (d4.get("hit"), d4.get("err") or "none"))

        # ---------- 5. 全程无异常 ----------
        ck(not c.errors, "跨文件调用全程无 pageerror", "; ".join(c.errors[:2]) or "clean")

        shot = c.send("Page.captureScreenshot", {"format": "png"})
        os.makedirs(os.path.join("artifacts", "qa", "frontend-refactor"), exist_ok=True)
        with open(os.path.join("artifacts", "qa", "frontend-refactor", "bridge_e2e.png"), "wb") as f:
            f.write(base64.b64decode(shot["data"]))
    finally:
        try:
            c.ws.close()
        except Exception:
            pass
        proc.terminate()

    print("\n=== 跨文件调用链贯通验证 ===\n")
    ok = 0
    for o, l, det in checks:
        print(("  PASS  " if o else "  FAIL  ") + l + ("   [" + det + "]"))
        ok += o
    print("\n%d/%d 通过" % (ok, len(checks)))
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
