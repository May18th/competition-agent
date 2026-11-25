"""线上「没选赛道不许生成」闸门测试（不消耗额度）。

做法：在浏览器侧把 /api/generate_async 掐死（fetch 直接 reject、XHR 打标），
然后点真实按钮 #startBtn，观察两件事：
  ① 未选赛道时：只弹提示、不发请求（闸门生效）；
  ② 选了赛道后：请求确实发出去了（闸门没有误拦）。
请求在本地就被拦掉，不会真的走后端，不消耗线上配额。
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
PORT = 9371


def main():
    profile = tempfile.mkdtemp(prefix="gate-")
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
        "--proxy-server=http://127.0.0.1:7897",
        f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
        f"--user-data-dir={profile}", "--window-size=1280,1000", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    out = {"steps": [], "ok": True}
    def step(n, v, e=None):
        ok = True if e is None else str(v) == str(e)
        out["steps"].append({"step": n, "value": v, "expect": e, "ok": ok})
        if not ok:
            out["ok"] = False

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
        c = websocket.create_connection(ws_url, timeout=40)
        n = [0]

        def send(m, **pr):
            n[0] += 1
            mid = n[0]
            c.send(json.dumps({"id": mid, "method": m, "params": pr}))
            while True:
                r = json.loads(c.recv())
                if r.get("id") == mid:
                    return r

        def js(e):
            e = e.strip()
            if e.startswith('() =>') or e.startswith('()=>'):
                e = '(' + e + ')()'
            r = send("Runtime.evaluate", expression=e, returnByValue=True, userGesture=True)
            if r.get("result", {}).get("exceptionDetails"):
                return "ERR:" + str(r["result"]["exceptionDetails"].get("text"))
            return r.get("result", {}).get("result", {}).get("value")

        send("Page.navigate", url=BASE)
        for _ in range(60):
            if js("document.readyState") == "complete":
                break
            time.sleep(0.3)
        time.sleep(3)

        # 关引导 + 掐断生成请求 + 填一句创意
        js("""() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='知道了'); if(b) b.click(); return 1; }""")
        js("""() => {
            window.__genTried = [];
            const of = window.fetch;
            window.fetch = function(u, o){
                const s = String(u);
                if (s.indexOf('generate') >= 0) { window.__genTried.push(s); return Promise.reject(new Error('blocked-by-test')); }
                return of.apply(this, arguments);
            };
            const ox = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(m, u){
                if (String(u).indexOf('generate') >= 0) window.__genTried.push('xhr:' + u);
                return ox.apply(this, arguments);
            };
            const ta = document.getElementById('idea');
            if (ta) { ta.value = '面向大学城学生的智能取件柜，解决快递最后一百米取件排队问题'; ta.dispatchEvent(new Event('input', {bubbles:true})); }
            return 'armed';
        }""")
        time.sleep(1)
        js("""() => { const el=document.querySelector('#compQuickRow [data-comp*="iCAN"]'); if(el) el.click(); return 1; }""")
        time.sleep(2)

        step("尚未选赛道时徽章", js("(document.getElementById('evTrackBadge').textContent||'').trim()"), "待选赛道")
        step("清空历史选择", js("""() => { try { for (const k of Object.keys(localStorage)) if (k.indexOf('wb')>=0 || k.indexOf('comp')>=0) localStorage.removeItem(k); } catch(e) {} return 'cleared'; }"""))
        js("""() => { const el=document.querySelector('#compQuickRow [data-comp*="iCAN"]'); if(el) el.click(); return 1; }""")
        time.sleep(2)
        step("清空后徽章", js("(document.getElementById('evTrackBadge').textContent||'').trim()"), "待选赛道")

        # 点生成（应当被拦）
        js("document.getElementById('startBtn').click(); 1")
        time.sleep(2.5)
        step("拦截后是否发出请求", js("window.__genTried.length"), 0)
        step("提示文案", js("""() => { const t=document.getElementById('wbToast'); return t ? (t.textContent||'').replace(/\\s+/g,' ').trim().slice(0,80) : 'no-toast'; }"""))
        step("按钮是否恢复可点", js("!document.getElementById('startBtn').disabled"), True)
        shot = send("Page.captureScreenshot", format="png")
        open(os.path.join(OUT, "prod_gate_blocked.png"), "wb").write(base64.b64decode(shot["result"]["data"]))

        # 选一条赛道后再点，应当放行
        js("document.getElementById('evTrackBadge').click(); 1")
        time.sleep(1)
        step("打开后路片数", js("document.querySelectorAll('#evTrackChips .ev-track-chip').length"), 3)
        js("""() => { const cs=[...document.querySelectorAll('#evTrackChips .ev-track-chip')]; cs[1].click(); return 1; }""")
        time.sleep(1.5)
        step("已选赛道", js("(document.getElementById('evTrackBadge').textContent||'').trim()"))
        js("document.getElementById('startBtn').click(); 1")
        time.sleep(3)
        step("选后是否会发请求（>0 表示放行）", js("window.__genTried.length"))
        step("放行后提示", js("""() => { const t=document.getElementById('wbToast'); return t ? (t.textContent||'').replace(/\\s+/g,' ').trim().slice(0,60) : 'no-toast'; }"""))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
