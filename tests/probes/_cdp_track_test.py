"""赛道徽章功能实测（CDP 驱动真实 Chrome，不依赖浏览器 MCP）。

跑法：
    python tests/probes/_cdp_track_test.py [base_url]

做的事：打开首页 → 选 iCAN → 展开赛事卡 → 点赛道路片 → 校验徽章回执 / aria-pressed /
日间夜间配色 / 控制台报错，并把截图存到 .workbuddy/artifacts-archive/qa/。
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
OUT = os.path.join(".workbuddy", "artifacts-archive", "qa")
PORT = 9333


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.n = 0
        self.errors = []
        self.console = []

    def send(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"].get("exceptionDetails", {})
                self.errors.append(str(d.get("text")) + " " + str(d.get("exception", {}).get("description", ""))[:300])
            elif msg.get("method") == "Log.entryAdded":
                e = msg["params"]["entry"]
                if e.get("level") in ("error", "warning") and "favicon" not in str(e.get("url")):
                    self.console.append(f"[{e.get('level')}] {e.get('text')[:200]}")
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr, wait=True):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=wait, userGesture=True)
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            return {"__error__": str(r["exceptionDetails"].get("text"))}
        return res.get("value")

    def shot(self, path, full=False):
        r = self.send("Page.captureScreenshot", format="png", captureBeyondViewport=full)
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return path


def wait_ready(cdp, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cdp.js("document.readyState") == "complete":
            return True
        time.sleep(0.2)
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="cdp-track-")
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--no-proxy-server", "--hide-scrollbars", f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        # 页面 head 里有三个 jsdelivr CDN 脚本，本地网络连不上会一直等、把整页解析卡住；
        # 把外部域名解析到黑洞，让它们立刻失败，走页面自带的本地方案
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
        f"--user-data-dir={profile}", "--window-size=1280,1000", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = {"steps": [], "ok": True}
    try:
        ws_url = None
        for _ in range(60):
            try:
                data = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/json/list", timeout=3).read())
                pages = [t for t in data if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if not ws_url:
            raise RuntimeError("拿不到 CDP websocket")

        cdp = CDP(ws_url)
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Log.enable")
        cdp.send("Page.navigate", url=BASE)
        wait_ready(cdp)
        time.sleep(3)  # 等 competition_index.json / 主题脚本就位

        def step(name, value, expect=None, note=""):
            ok = True if expect is None else (value == expect)
            result["steps"].append({"step": name, "value": value, "expect": expect, "ok": ok, "note": note})
            if not ok:
                result["ok"] = False

        step("页面标题", cdp.js("document.title"))
        step("赛事清单已加载", cdp.js("(document.querySelectorAll('#competitionList option')||[]).length > 0"), True)

        # 选 iCAN（走输入框 + input 事件，和真人输入同一条链路）
        cdp.js("""() => {
            const i = document.getElementById('competition');
            i.value = 'iCAN';
            i.dispatchEvent(new Event('input', {bubbles: true}));
            i.dispatchEvent(new Event('change', {bubbles: true}));
            return i.value;
        }""")
        time.sleep(1.5)
        step("赛事卡显示", cdp.js("getComputedStyle(document.getElementById('eventReqCard')).display") != "none", True)
        step("赛道徽章初始文案（未选=待选）", cdp.js("(document.getElementById('evTrackBadge')||{}).textContent||''"))

        # 默认收起时：赛道盒子应该在 evBody 里看不见
        step("赛道盒子初始可见性", cdp.js("""() => {
            const b = document.getElementById('evTrackBox');
            if (!b) return 'missing';
            return b.offsetParent === null ? 'hidden' : 'visible';
        }"""))
        cdp.shot(os.path.join(OUT, "track_local_collapsed_light.png"))

        # 点徽章：展开并滚到赛区块
        cdp.js("document.getElementById('evTrackBadge').click(); true")
        time.sleep(1.2)
        step("点徽章后赛道盒子", cdp.js("""() => {
            const b = document.getElementById('evTrackBox');
            return b && b.offsetParent !== null ? 'visible' : 'hidden';
        }"""), "visible")
        step("赛道路片数量", cdp.js("document.querySelectorAll('#evTrackChips .ev-track-chip').length"))
        step("chips 高度够点（>=38）", cdp.js("""() => {
            const c = document.querySelector('.ev-track-chip');
            return c ? Math.round(c.getBoundingClientRect().height) : 0;
        }"""))
        cdp.shot(os.path.join(OUT, "track_local_expanded_light.png"))

        # 选第二条赛道
        picked = cdp.js("""() => {
            const cs = [...document.querySelectorAll('#evTrackChips .ev-track-chip')];
            if (cs.length < 2) return null;
            cs[1].click();
            return cs[1].textContent.trim();
        }""")
        time.sleep(1.2)
        step("已点选赛道", picked)
        step("aria-pressed 正确", cdp.js("""() => {
            const cs = [...document.querySelectorAll('#evTrackChips .ev-track-chip')];
            return cs.map(c => c.getAttribute('aria-pressed')).join(',');
        }"""))
        step("徽章回执文案", cdp.js("(document.getElementById('evTrackBadge')||{}).textContent||''"))
        cdp.shot(os.path.join(OUT, "track_local_selected_light.png"))

        # 日间可读性：徽章与 chip 的对比取样
        step("日间徽章配色", cdp.js("""() => {
            const b = document.getElementById('evTrackBadge');
            const s = getComputedStyle(b);
            return [s.color, s.backgroundColor, s.borderColor].join(' | ');
        }"""))
        step("日间选中 chip 配色", cdp.js("""() => {
            const c = document.querySelector('.ev-track-chip[aria-pressed="true"]');
            if (!c) return 'none';
            const s = getComputedStyle(c);
            return [s.color, s.backgroundColor].join(' | ');
        }"""))

        # 切夜间
        cdp.js("document.body.classList.remove('light'); true")
        time.sleep(0.6)
        step("夜间选中 chip 配色", cdp.js("""() => {
            const c = document.querySelector('.ev-track-chip[aria-pressed="true"]');
            const s = getComputedStyle(c);
            return [s.color, s.backgroundColor].join(' | ');
        }"""))
        cdp.shot(os.path.join(OUT, "track_local_selected_dark.png"))
        cdp.js("document.body.classList.add('light'); true")

        # 手机宽度
        cdp.send("Emulation.setDeviceMetricsOverride", width=375, height=812,
                 deviceScaleFactor=2, mobile=True)
        time.sleep(1.0)
        step("375 下 chips 是否溢出", cdp.js("""() => {
            const box = document.getElementById('evTrackChips');
            if (!box) return 'missing';
            return box.scrollWidth - box.clientWidth > 1 ? ('overflow ' + (box.scrollWidth - box.clientWidth)) : 'no-overflow';
        }"""), "no-overflow")
        step("375 下 chip 高度", cdp.js("""() => {
            const c = document.querySelector('.ev-track-chip');
            return c ? Math.round(c.getBoundingClientRect().height) : 0;
        }"""))
        cdp.shot(os.path.join(OUT, "track_local_375_light.png"))

        result["jsErrors"] = cdp.errors
        result["consoleIssues"] = cdp.console[:15]
        if cdp.errors:
            result["ok"] = False
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
