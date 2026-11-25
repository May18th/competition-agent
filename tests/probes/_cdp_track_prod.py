"""线上真实点击测试：kechuang2026.cn 的赛道选择链路。

走 Clash 代理（本地直连外网受限），CDP 驱动真实 Chrome，模拟真人：
选 iCAN → 看徽章初始态 → 点徽章展开 → 点第 2 条赛道 → 校验回执/aria-pressed →
刷新后校验已选状态是否保留。不点「开始生成」，避免消耗线上配额。
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
BASE = sys.argv[1] if len(sys.argv) > 1 else "https://kechuang2026.cn/"
OUT = os.path.join(".workbuddy", "artifacts-archive", "qa")
PORT = 9360


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=40)
        self.n = 0
        self.errors = []

    def send(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"].get("exceptionDetails", {})
                self.errors.append((str(d.get("text")) + " " +
                                    str(d.get("exception", {}).get("description", ""))[:200]).strip())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        # 传进来的箭头函数必须自执行，否则 evaluate 只会返回一个函数对象（拿到空 {}）
        e = expr.strip()
        if e.startswith('() =>') or e.startswith('()=>') or e.startswith('(function'):
            expr = '(' + e + ')()'
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True)
        if r.get("exceptionDetails"):
            return {"__error__": str(r["exceptionDetails"].get("text"))}
        return r.get("result", {}).get("value")

    def shot(self, name):
        r = self.send("Page.captureScreenshot", format="png")
        p = os.path.join(OUT, name)
        open(p, "wb").write(base64.b64decode(r["data"]))
        return p


def main():
    os.makedirs(OUT, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="cdp-prod-")
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--proxy-server=http://127.0.0.1:7897",
        f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
        f"--user-data-dir={profile}", "--window-size=1280,1000", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    out = {"url": BASE, "steps": [], "ok": True}
    step = lambda n, v, e=None: (out["steps"].append(
        {"step": n, "value": v, "expect": e,
         "ok": True if e is None else (str(v) == str(e))}),
        None if e is None or str(v) == str(e) else out.update(ok=False))
    try:
        ws_url = None
        for _ in range(60):
            try:
                d = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/json/list", timeout=3).read())
                pg = [t for t in d if t.get("type") == "page"]
                if pg:
                    ws_url = pg[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.3)
        cdp = CDP(ws_url)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Page.navigate", url=BASE)
        for _ in range(60):
            if cdp.js("document.readyState") == "complete":
                break
            time.sleep(0.3)
        time.sleep(3)

        step("页面加载", cdp.js("document.readyState"), "complete")
        step("赛事清单选项数", cdp.js("document.querySelectorAll('#competitionList option').length"))

        # 走真实入口：点赛事快捷按钮（data-wbcomp），等价于用户点一下 iCAN
        # 先关掉新手引导浮层（真实用户也是点「知道了」）
        step("引导层存在", cdp.js("!!document.getElementById('wbCoachVeil')"))
        step("点掉引导", cdp.js("""() => {
            const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='知道了');
            if(b){ b.click(); return 'clicked'; }
            const v=document.getElementById('wbCoachVeil'); if(v){ v.click(); return 'veil'; }
            return 'none';
        }"""))
        time.sleep(0.8)
        step("引导层已消失", cdp.js("!document.getElementById('wbCoachVeil')"))

        # 走真实入口：点紧凑的赛事 chip（data-comp + wbPickComp）
        step("快捷按钮数", cdp.js("document.querySelectorAll('#compQuickRow [data-comp]').length"))
        step("点 iCAN", cdp.js("""() => {
            const el=document.querySelector('#compQuickRow [data-comp*="iCAN"]');
            if(!el) return 'no-chip';
            el.click(); return 'clicked:' + el.getAttribute('data-comp');
        }"""))
        time.sleep(2.5)
        step("输入框值", cdp.js("document.getElementById('competition').value"))

        step("赛事卡可见", cdp.js("getComputedStyle(document.getElementById('eventReqCard')).display"), "block")
        step("徽章初始文案", cdp.js("(document.getElementById('evTrackBadge').textContent||'').trim()"))
        cdp.shot("prod_track_1_initial.png")

        # 点徽章
        cdp.js("document.getElementById('evTrackBadge').click(); true")
        time.sleep(1.2)
        step("点徽章后赛道盒可见", cdp.js(
            "document.getElementById('evTrackBox').offsetParent!==null"), True)
        step("赛道路片数", cdp.js("document.querySelectorAll('#evTrackChips .ev-track-chip').length"))
        step("路片文案", cdp.js(
            "[...document.querySelectorAll('#evTrackChips .ev-track-chip')].map(c=>c.textContent.trim()).join('/')"))
        step("路片高度", cdp.js(
            "Math.round(document.querySelector('.ev-track-chip').getBoundingClientRect().height)"))
        cdp.shot("prod_track_2_expanded.png")

        # 点第二条赛道
        picked = cdp.js("""() => { const cs=[...document.querySelectorAll('#evTrackChips .ev-track-chip')];
            if(cs.length<2) return null; cs[1].click(); return cs[1].textContent.trim(); }""")
        time.sleep(1.5)
        step("已点选", picked)
        step("aria-pressed", cdp.js(
            "[...document.querySelectorAll('#evTrackChips .ev-track-chip')].map(c=>c.getAttribute('aria-pressed')).join(',')"))
        step("徽章回执", cdp.js("(document.getElementById('evTrackBadge').textContent||'').trim()"))
        step("未选提醒条是否已隐藏", cdp.js(
            "getComputedStyle(document.getElementById('evTrackWarn')).display"), "none")
        cdp.shot("prod_track_3_selected.png")

        # 刷新后持久化
        cdp.send("Page.reload")
        time.sleep(1)
        for _ in range(60):
            if cdp.js("document.readyState") == "complete":
                break
            time.sleep(0.3)
        time.sleep(3)
        step("刷新后赛事卡可见", cdp.js(
            "getComputedStyle(document.getElementById('eventReqCard')).display"), "block")
        step("刷新后徽章文案", cdp.js("(document.getElementById('evTrackBadge').textContent||'').trim()"))
        step("刷新后选中 chip", cdp.js("""() => { const c=document.querySelector('#evTrackChips .ev-track-chip[aria-pressed="true"]');
            return c ? c.textContent.trim() : 'none'; }"""))
        cdp.shot("prod_track_4_persist.png")

        out["jsErrors"] = [e for e in cdp.errors if "favicon" not in e][:8]
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
