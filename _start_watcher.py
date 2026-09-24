# -*- coding: utf-8 -*-
"""把 _watcher.py 拉成脱离控制台的常驻进程，并写进注册表 Run 键开机自启。
不需要管理员权限。幂等。
"""
import os
import subprocess
import sys
import time
import winreg

sys.stdout.reconfigure(encoding='utf-8')

PYW = r'C:\Users\34984\.conda\envs\rag-dev\pythonw.exe'
PROJECT_DIR = r'C:\Users\34984\Doubao\chats\2026-09-23\new-chat\科创赛事助手'
WATCHER = os.path.join(PROJECT_DIR, '_watcher.py')
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = '科创赛事助手守护'

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
DETACH = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def running_pids():
    """已有多少个 _watcher.py 进程"""
    try:
        out = subprocess.run(
            ['wmic', 'PROCESS', 'WHERE', 'name="pythonw.exe"', 'GET', 'ProcessId,CommandLine', '/VALUE'],
            capture_output=True, text=True, encoding='utf-8', errors='ignore').stdout
        pids = []
        for b in out.replace('\r', '').split('\n\n'):
            if '_watcher.py' in b:
                m = __import__('re').search(r'ProcessId=(\d+)', b)
                if m:
                    pids.append(int(m.group(1)))
        return pids
    except Exception:
        return []


print('=== 1. 拉起常驻守护 ===')
have = running_pids()
if have:
    print('  守护已在运行，PID:', have)
else:
    subprocess.Popen([PYW, WATCHER], cwd=PROJECT_DIR, creationflags=DETACH,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    print('  已拉起，等待确认...')
    for _ in range(8):
        time.sleep(1)
        p = running_pids()
        if p:
            print('  守护进程 PID:', p)
            break
    else:
        print('  ⚠ 8 秒内未检测到守护进程')

print()
print('=== 2. 注册开机自启（注册表 Run 键）===')
try:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        cmd = '"%s" "%s"' % (PYW, WATCHER)
        winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    print('  已写入:', VALUE_NAME)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
        v, _ = winreg.QueryValueEx(k, VALUE_NAME)
        print('  回读确认:', v)
except Exception as e:
    print('  注册失败:', repr(e))
