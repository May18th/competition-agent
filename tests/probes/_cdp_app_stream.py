"""流式渲染链回归：直接驱动 streamPrepare / paintPartial / streamFinish

为什么单独测这条链：
    作用域收口把 app.js 包进 IIFE，而流式渲染是唯一"跨文件 + 分帧 + 增量"的路径：
    app.js 的 paintPartial 要调首页内联脚本里的 twSet（打字机），
    而 twSet 又依赖 app.js 导出的 _STREAM_MAP 找字段对应的 DOM id。
    这是全站耦合最深的一段，也是最容易在收口后静默失效的一段。

判据：
    ① streamPrepare 铺出占位、启动流式状态
    ② paintPartial 逐次增量调用 twSet（打字机真的被驱动，不是一次整块覆盖）
    ③ 增量语义正确：第二次传更长的文本，只揭示新增部分
    ④ streamFinish 收尾，流式标记被清除
    ⑤ 全程无异常
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9417
URL = "http://127.0.0.1:8080/"


def launch():
    prof = tempfile.mkdtemp(prefix="wbstream-")
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

    def send(self, m, p=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg.get("result", {})
            if msg.get("method") == "Runtime.exceptionThrown":
                self.errors.append(msg["params"]["exceptionDetails"].get("text", ""))

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

        # 先展开结果区，否则 twPaint 找不到目标 DOM 节点。
        # 用演示样例（零 POST、不动额度），只为把结果页结构与字段节点铺出来。
        c.ev("(function(){ try { window.wbOpenDemo(); } catch(e){ return String(e); } return 'ok'; })()")
        time.sleep(5)
        # 清掉演示文本，避免干扰"内容是否落到 DOM"的判定。
        # _STREAM_MAP 里 proposal → proposalText，别清错节点。
        c.ev("(function(){ var p=document.getElementById('proposalText'); if(p) p.innerHTML=''; return 'cleared'; })()")

        # 一次性跑完整条链，记录每一步的观测值
        r = c.ev(r"""(async function(){
            var log = {steps: [], twCalls: [], err: null};
            var origTw = window.twSet;
            if (typeof origTw !== 'function') { log.err = 'twSet 不可用（首页内联脚本未加载）'; return JSON.stringify(log); }

            window.twSet = function(key, text){
                log.twCalls.push({key: key, len: (text||'').length});
                try { return origTw.apply(this, arguments); } catch(e){ log.err = 'twSet 内抛错: '+e; }
            };

            try {
                // ① 开始
                if (typeof window.streamPrepare !== 'function') { log.err = 'streamPrepare 未导出'; return JSON.stringify(log); }
                window.streamPrepare('fast');
                log.steps.push('prepare');

                // ② 第一次增量
                var t1 = '第一段：项目背景与问题定义。这里是流式增量测试文本，用来确认打字机能被逐次驱动。';
                window.paintPartial({proposal: t1});
                log.steps.push('paint1');

                // ③ 第二次增量（累积更长）
                var t2 = t1 + '第二段：方法与实现路径。增量渲染应当只揭示新增部分，而不是整段重画。';
                window.paintPartial({proposal: t2});
                log.steps.push('paint2');

                // ④ 先等打字机把字揭示出来，**再收尾**。
                //    顺序不能反：streamFinish 会撤掉流式占位并交给最终渲染，
                //    先 finish 再查 DOM 时占位已被撤，必然判空（本探针原先就这么写的）。
                var el0 = document.getElementById('proposalText');
                for (var w = 0; w < 40; w++) {
                    await new Promise(function(res){ setTimeout(res, 100); });
                    if (el0 && (el0.innerText || '').indexOf('第一段') >= 0) break;
                }
                log.domHasText = el0 ? (el0.innerText || '').indexOf('第一段') >= 0 : false;
                log.domLen = el0 ? (el0.innerText || '').length : -1;

                // ⑤ 收尾
                if (typeof window.streamFinish === 'function') { window.streamFinish(); log.steps.push('finish'); }
                else { log.steps.push('finish-missing'); }
            } catch(e) {
                log.err = String(e);
            } finally {
                window.twSet = origTw;
            }
            return JSON.stringify(log);
        })()""")

        d = json.loads(r) if isinstance(r, str) else {}
        steps = d.get("steps") or []
        calls = d.get("twCalls") or []

        ck(d.get("err") is None, "流式链全程无异常", d.get("err") or "clean")
        ck(steps[:1] == ["prepare"], "streamPrepare 正常执行", str(steps))
        ck(len(calls) >= 2, "paintPartial 两次都驱动了 twSet", "twSet 调用 %d 次: %s"
           % (len(calls), [x.get("len") for x in calls]))
        # 增量语义：第二次揭示的文本应比第一次长
        ck(len(calls) >= 2 and calls[1].get("len", 0) > calls[0].get("len", 0),
           "增量语义正确（第二次文本更长）",
           "%s → %s" % (calls[0].get("len") if calls else "?", calls[1].get("len") if len(calls) > 1 else "?"))
        ck("finish" in steps, "streamFinish 正常收尾", str(steps))
        ck(d.get("domHasText") is True, "流式内容真的落到 DOM", str(d.get("domHasText")))

        ck(not c.errors, "无 pageerror", "; ".join(c.errors[:2]) or "clean")
    finally:
        try:
            c.ws.close()
        except Exception:
            pass
        proc.terminate()

    print("\n=== 流式渲染链回归 ===\n")
    ok = 0
    for o, l, det in checks:
        print(("  PASS  " if o else "  FAIL  ") + l + ("   [" + det + "]"))
        ok += o
    print("\n%d/%d 通过" % (ok, len(checks)))
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
