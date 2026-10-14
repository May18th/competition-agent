#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用本地 http.server 重抓真实前端截图，避免 file:// 协议下 /static/style.css 丢失导致 SVG 巨大化。"""
import os, subprocess, time
from PIL import Image

REPO = os.path.dirname(os.path.abspath(__file__))
VID = os.path.join(REPO, "artifacts", "demo-video")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def capture():
    # 启动 http.server
    proc = subprocess.Popen(
        [r"C:\Users\34984\.workbuddy\binaries\python\versions\3.13.12\python.exe", "-m", "http.server", "8123"],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        time.sleep(1.5)
        for name, w, h, outname in [
            ("desktop", 1280, 2600, "real_ui_desktop.png"),
            ("mobile", 390, 3000, "real_ui_mobile.png"),
        ]:
            out = os.path.join(VID, outname)
            cmd = [
                EDGE, "--headless=new", "--disable-gpu",
                f"--screenshot={out}", f"--window-size={w},{h}",
                "--hide-scrollbars", "--virtual-time-budget=7000",
                "http://127.0.0.1:8123/index.html"
            ]
            subprocess.run(cmd, capture_output=True, timeout=20)
            print(name, "saved", os.path.exists(out), out)
        # 从桌面截图顶部裁出 16:9 hero
        d = Image.open(os.path.join(VID, "real_ui_desktop.png"))
        hero = d.crop((0, 0, 1280, 720))
        hero.save(os.path.join(VID, "hero_desktop.png"))
        print("hero saved")
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except: proc.kill()

if __name__ == "__main__":
    capture()
