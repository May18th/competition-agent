# -*- coding: utf-8 -*-
"""探针用静态服务：站点根 = frontend/，额外把 tests/probes/*.html 挂在 /__probe/ 下。

用途：index.html 里全是 /static/... 绝对路径，必须让 frontend/ 当站点根才能跑；
又不能让探针壳文件落进 frontend/（会被部署上云），所以多挂一个只读路由。
"""
import os
import sys
import functools
import urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONTEND = os.environ.get("SERVE_DIR") or os.path.join(ROOT, "frontend")
PROBES = os.path.dirname(os.path.abspath(__file__))
# 设了 UPSTREAM 就走反向代理：/__probe/* 读本地探针文件，其余全部转发给真后端。
# 这样探针和页面同源，能 iframe + 脚本化；同时跑的是真接口（真赛道数据），不是桩。
UPSTREAM = os.environ.get("UPSTREAM", "").rstrip("/")


class H(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/__probe/"):
            rel = path[len("/__probe/"):]
            base, root = rel, PROBES
        else:
            base, root = path.lstrip("/"), FRONTEND
        parts = [p for p in base.split("/") if p not in ("", ".", "..")]
        return os.path.join(root, *parts)

    def _proxy(self):
        url = UPSTREAM + self.path
        body = None
        ln = self.headers.get("Content-Length")
        if ln:
            body = self.rfile.read(int(ln))
        req = urllib.request.Request(url, data=body, method=self.command)
        for k in ("Content-Type", "Accept", "Cookie"):
            if self.headers.get(k):
                req.add_header(k, self.headers[k])
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() in ("transfer-encoding", "connection", "content-length"):
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # 上游没起来时给个明确 502，别静默挂住
            msg = ("upstream error: %s" % e).encode()
            self.send_response(502)
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self):
        if self.path.split("?")[0].endswith("/static/sw.js"):
            # 探针环境一律不注册 SW：headless 里 SW 安装会一直占着网络空闲判定，
            # --dump-dom / --screenshot 直接挂死不返回（实测 timeout 120s 仍空）。
            self.send_error(404, "no sw in probe")
            return
        if UPSTREAM and not self.path.split("?")[0].startswith("/__probe/"):
            return self._proxy()
        p = self.path.split("?")[0]
        # 赛事结构化配置给个桩：赛道数据只在这份 JSON 里（iCAN 三赛道 / 互联网+ 九组），
        # 拿不到就永远只有「通用规则」，赛道相关的 UI 全都不出现，验不了。
        if p == "/api/competition_profiles":
            src = os.path.join(ROOT, "backend", "assets", "data", "competition_profiles.json")
            if os.path.exists(src):
                self._json(open(src, "rb").read())
                return
        if p == "/api/stats":
            self._json(b'{"success":true,"stats":{}}')
            return
        SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        if UPSTREAM:
            return self._proxy()
        self.send_error(404)

    def _json(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    print("serving %s at http://127.0.0.1:%d/" % (FRONTEND, port))
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
