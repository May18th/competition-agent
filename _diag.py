# -*- coding: utf-8 -*-
"""诊断：用守护完全相同的方式拉起 Flask，把 stderr 抓到文件里看它为什么起不来。"""
import os
import socket
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

PYW = r'C:\Users\34984\.conda\envs\rag-dev\pythonw.exe'
PROJECT_DIR = r'C:\Users\34984\Doubao\chats\2026-09-23\new-chat\科创赛事助手'
ERR = os.path.join(PROJECT_DIR, '_diag_err.txt')

DETACH = 0x00000008 | 0x00000200 | 0x08000000


def http_ok(port=8080, timeout=2):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(('127.0.0.1', port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


print('=== 现状 ===')
print('8080 已监听:', http_ok())

print()
print('=== 诊断 1：pythonw + DETACH + DEVNULL（守护用的方式）===')
with open(ERR, 'w') as f:
    p = subprocess.Popen([PYW, 'run.py'], cwd=PROJECT_DIR, creationflags=DETACH,
                         stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                         close_fds=True)
print('  已发起，PID', p.pid)
for i in range(15):
    time.sleep(1)
    if http_ok():
        print('  ✔ %d 秒后端口可用' % (i + 1))
        break
else:
    print('  ❌ 15 秒仍不可用')
print('  3 秒后进程是否还活着:', end=' ')
time.sleep(3)
chk = subprocess.run(['tasklist', '/FI', 'PID eq %d' % p.pid],
                     capture_output=True, text=True, encoding='utf-8', errors='ignore').stdout
print('在' if str(p.pid) in chk else '❌ 已消失')

print()
print('=== 错误输出 ===')
if os.path.exists(ERR):
    txt = open(ERR, encoding='utf-8', errors='ignore').read()
    print(txt if txt.strip() else '(空 —— 说明进程没能输出任何东西就被结束了)')
