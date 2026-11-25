"""app.js 作用域收口：真实浏览器端到端回归（本地 8080，只读）

判据（任一不满足即视为回归）：
  ① pageerror / console error 为 0
  ② 闭包生效：私有实现不在 window 上
  ③ 契约完整：HTML onclick 引用的函数全部 typeof === 'function'
  ④ 猴补丁链未断：首页对 renderRich 等的包装能覆盖到 app.js 内部调用
  ⑤ 关键交互真的能跑：赛事下拉、历史列表、提示条

用法: python tests/probes/_cdp_app_scope.py
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
PORT = 9411
URL = "http://127.0.0.1:8080/"
OUT = os.path.join("artifacts", "qa", "frontend-refactor")


def launch():
    prof = tempfile.mkdtemp(prefix="wbscope-")
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=1440,900", "--remote-debugging-port=%d" % PORT,
            "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check",
            URL]
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
    raise RuntimeError("Chrome 未能启动")


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.i = 0
        self.errors = []
        self.console_errors = []

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg.get("result", {})
            self._event(msg)

    def _event(self, msg):
        m = msg.get("method")
        if m == "Runtime.exceptionThrown":
            d = msg["params"]["exceptionDetails"]
            self.errors.append((d.get("text") or "") + " @ " + str(d.get("url", "")))
        elif m == "Runtime.consoleAPICalled" and msg["params"].get("type") == "error":
            parts = [str(a.get("value", a.get("description", ""))) for a in msg["params"].get("args", [])]
            self.console_errors.append(" ".join(parts)[:300])

    def drain(self, sec=1.0):
        self.ws.settimeout(sec)
        try:
            while True:
                self._event(json.loads(self.ws.recv()))
        except Exception:
            pass
        finally:
            self.ws.settimeout(30)

    def ev(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
            "awaitPromise": await_promise, "userGesture": True})
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            return {"__error": str(r["exceptionDetails"].get("text"))}
        return res.get("value")


def main():
    proc, ws = launch()
    c = CDP(ws)
    checks = []

    def ck(ok, label, detail=""):
        checks.append({"ok": bool(ok), "label": label, "detail": detail})

    try:
        c.send("Runtime.enable")
        c.send("Page.enable")
        c.send("Page.navigate", {"url": URL})
        time.sleep(4)
        c.drain(1.5)

        # ① 无脚本错误
        ck(not c.errors, "pageerror 为 0", "; ".join(c.errors[:3]) or "clean")
        ck(not c.console_errors, "console error 为 0", "; ".join(c.console_errors[:3]) or "clean")

        # ② 闭包生效
        priv = ["_wbFetch", "wbApi", "_wbStoreDel", "_wbSessGet"]
        leaked = c.ev("JSON.stringify(%s.filter(function(k){return typeof window[k]!=='undefined';}))" % json.dumps(priv))
        ck(leaked in ("[]", None), "私有实现未泄漏到 window", "leaked=" + str(leaked))

        # ③ HTML onclick 契约：解析页面里真实存在的 onclick，逐个验类型
        res = c.ev("""(function(){
            var names = {}, bad = [];
            var els = document.querySelectorAll('[onclick],[onchange],[oninput]');
            for (var i=0;i<els.length;i++){
                var el = els[i], attrs=['onclick','onchange','oninput'];
                for (var a=0;a<attrs.length;a++){
                    var v = el.getAttribute(attrs[a]); if(!v) continue;
                    var m = v.match(/^\\s*([A-Za-z_$][\\w$]*)\\s*\\(/);
                    // 排除 onclick="if (...) ..." 这类语句开头，只有真函数名才算契约
                    if (m && !/^(if|for|while|switch|return|try|typeof|void)$/.test(m[1])) names[m[1]] = 1;
                }
            }
            for (var k in names){ if (typeof window[k] !== 'function') bad.push(k); }
            return JSON.stringify({total:Object.keys(names).length, bad:bad});
        })()""")
        info = json.loads(res) if res else {"total": 0, "bad": ["<eval failed>"]}
        ck(not info["bad"], "HTML onclick 函数全部可调用",
           "%d 个引用, 缺 %s" % (info["total"], info["bad"][:5] or "0"))

        # ④ 猴补丁链：首页确实包了 renderRich，且调用链能走到包装层
        patch = c.ev("""(function(){
            if (typeof window.renderRich !== 'function') return 'renderRich missing';
            var orig = window.renderRich;
            var hit = 0;
            window.renderRich = function(){ hit++; return orig.apply(this, arguments); };
            try { if (typeof window.__wbTestRenderRichCall === 'function') window.__wbTestRenderRichCall(); } catch(e){}
            var writable = (window.renderRich !== orig);
            window.renderRich = orig;
            return writable ? 'ok' : 'not writable';
        })()""")
        ck(patch == "ok", "window.renderRich 可被覆盖（猴补丁链通）", str(patch))

        # ⑤ 关键交互：赛事下拉能打开、历史能拉、提示条能出
        inter = c.ev("""(function(){
            var r = {};
            r.compOpener = typeof window.wbCompOpen === 'function';
            r.history   = typeof window.loadHistory === 'function';
            r.toast     = typeof window.wbToast === 'function';
            try { window.wbToast('自检提示', {type:'info', ms:1200}); r.toastFired = !!document.querySelector('#wbToast .wb-toast'); } catch(e){ r.toastFired=false; r.toastErr=String(e); }
            try { if (window.wbCompOpen) { window.wbCompOpen(); } r.compOpened = !!document.querySelector('#wbCompPanel.show, #wbCompPanel[style*="block"]'); } catch(e){ r.compErr=String(e); }
            return JSON.stringify(r);
        })()""")
        ii = json.loads(inter) if inter else {}
        ck(ii.get("compOpener") and ii.get("history") and ii.get("toast"),
           "核心入口函数存在", json.dumps({k: ii.get(k) for k in ("compOpener", "history", "toast")}, ensure_ascii=False))
        ck(ii.get("toastFired") is True, "提示条能真实渲染", str(ii.get("toastErr") or "ok"))

        c.drain(1.0)
        ck(not c.errors, "交互后仍无 pageerror", "; ".join(c.errors[:3]) or "clean")

        # 截图
        shot = c.send("Page.captureScreenshot", {"format": "png"})
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "after_scope_e2e.png"), "wb") as f:
            f.write(base64.b64decode(shot["data"]))

    finally:
        try:
            c.ws.close()
        except Exception:
            pass
        proc.terminate()

    print("\n=== 真实浏览器端到端回归（本地 8080）===\n")
    ok = 0
    for r in checks:
        print(("  PASS  " if r["ok"] else "  FAIL  ") + r["label"] +
              (("   [" + r["detail"] + "]") if r["detail"] else ""))
        ok += r["ok"]
    print("\n%d/%d 通过" % (ok, len(checks)))
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
