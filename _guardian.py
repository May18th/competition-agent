# -*- coding: utf-8 -*-
"""科创赛事助手 · 服务守护（Flask + cpolar 隧道）

被 Windows 计划任务每 3 分钟调用一次：
  1. 探 Flask（直连 socket，绕开系统代理），不通则拉起（完全脱离控制台，不会被回收）
  2. 探 cpolar 管理面板 9200，不在则拉起 cpolar
  3. 从 cpolar 隧道日志抓取最新公网地址，写入「公网地址.txt」

可以手工双击运行，也可以被计划任务调用。幂等：服务正常时什么都不做。
"""
import os
import re
import socket
import subprocess
import sys
import time

PY_EXE = r'C:\Users\34984\.conda\envs\rag-dev\python.exe'
PYW_EXE = r'C:\Users\34984\.conda\envs\rag-dev\pythonw.exe'
CPOLAR_BIN = r'D:\cpolar'          # 无扩展名可执行文件
CPOLAR_SVC = 'cpolar'              # 已注册为 Windows 服务，会自动重连，无需自己拉起
PROJECT_DIR = r'C:\Users\34984\Doubao\chats\2026-09-23\new-chat\科创赛事助手'
CPOLAR_LOG_DIR = r'C:\Users\34984\.cpolar\logs'
PUBLIC_URL_FILE = os.path.join(PROJECT_DIR, '公网地址.txt')

FLAG = 0
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
DETACH = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

LOG = []
KEY = 'ic_keyijianzhi'      # 后台标识，用于精准定位自己启动的进程
KEYWORDS = ['kechuang', 'ic_keyijianzhi']   # 进程关键词


def log(msg):
    line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
    LOG.append(line)
    try:
        print(line)
    except Exception:
        pass


def http_ok(host, port, path='/', timeout=5):
    """直连 socket 探活，不走系统代理"""
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        req = ('GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n'
               'User-Agent: guardian\r\n\r\n' % (path, host)).encode()
        s.sendall(req)
        head = s.recv(300)
        return b'HTTP' in head and b'200' in head.split(b'\r\n')[0]
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def port_pid(port):
    """找出监听该端口的 PID（可能多个，返回列表）"""
    pids = []
    try:
        out = subprocess.run(['netstat', '-ano'], capture_output=True,
                             text=True, encoding='utf-8', errors='ignore').stdout
        for ln in out.splitlines():
            if ':%s ' % port in ln and 'LISTENING' in ln:
                p = ln.strip().split()[-1]
                if p.isdigit():
                    pids.append(p)
    except Exception:
        pass
    return sorted(set(pids))


def kill_pid(pid):
    subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                   capture_output=True, text=True, errors='ignore')


def start_flask():
    """用 pythonw 无窗口启动，彻底脱离任何控制台"""
    try:
        subprocess.Popen([PYW_EXE, 'run.py'], cwd=PROJECT_DIR,
                         creationflags=DETACH,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         close_fds=True)
        return True
    except Exception as e:
        log('Flask 启动失败: %r' % e)
        return False


def fetch_public_url():
    """从 cpolar 今天的日志里抓最新的公网地址"""
    today = time.strftime('%Y%m%d')
    cand = []
    try:
        for fn in os.listdir(CPOLAR_LOG_DIR):
            if today in fn and fn.endswith('.log'):
                p = os.path.join(CPOLAR_LOG_DIR, fn)
                try:
                    with open(p, encoding='utf-8', errors='ignore') as f:
                        txt = f.read()
                except Exception:
                    continue
                for m in re.finditer(r'https?://[a-z0-9]+\.(?:r\d+\.(?:vip\.)?cpolar\.(?:cn|top|io)|cpolar\.(?:cn|top|io))', txt):
                    cand.append((os.path.getmtime(p), m.group(0)))
    except Exception as e:
        log('读 cpolar 日志失败: %r' % e)
    if not cand:
        return None
    cand.sort()
    return cand[-1][1]


def write_url(url):
    try:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(PUBLIC_URL_FILE, 'w', encoding='utf-8') as f:
            f.write('# 科创赛事助手 · 公网访问地址\n')
            f.write('# 最后更新：%s\n' % ts)
            f.write('# 本文件由 _guardian.py 自动维护，服务重启后地址可能变化，以本文件为准。\n\n')
            f.write('%s\n' % url)
        return True
    except Exception as e:
        log('写地址文件失败: %r' % e)
        return False


# ---------------- 主流程 ----------------
def main():
    # 1) Flask 探活
    ok = http_ok('127.0.0.1', 8080)
    if ok:
        log('Flask 正常，跳过')
    else:
        log('Flask 无响应，清理僵尸占用的端口...')
        for pid in port_pid(8080):
            log('  终止占端口进程 %s' % pid)
            kill_pid(pid)
        time.sleep(1.5)
        log('启动 Flask...')
        if start_flask():
            # 等它起来
            for _ in range(20):
                time.sleep(1)
                if http_ok('127.0.0.1', 8080):
                    log('Flask 已恢复 ✔')
                    break
            else:
                log('Flask 启动后 20 秒仍未响应')

    # 2) cpolar 状态（已注册为 Windows 服务，系统会自动拉起，这里只做观察与兜底）
    try:
        svc = subprocess.run(['sc', 'query', CPOLAR_SVC], capture_output=True,
                             text=True, encoding='utf-8', errors='ignore').stdout
        cpolar_running = 'RUNNING' in svc
    except Exception:
        cpolar_running = False

    if cpolar_running:
        log('cpolar 服务运行中')
    else:
        log('cpolar 服务未运行，尝试拉起...')
        try:
            subprocess.run(['sc', 'start', CPOLAR_SVC], capture_output=True,
                           text=True, errors='ignore')
            time.sleep(3)
        except Exception as e:
            log('cpolar 拉起失败: %r' % e)

    # 3) 抓公网地址落盘
    url = fetch_public_url()
    if url:
        https = url.replace('http://', 'https://')
        write_url(https)
        log('公网地址已更新 → %s' % https)
    else:
        log('未取到公网地址')

    # 4) 写运行日志
    try:
        with open(os.path.join(PROJECT_DIR, 'guardian.log'), 'a', encoding='utf-8') as f:
            f.write('\n'.join(LOG) + '\n')
    except Exception:
        pass


if __name__ == '__main__':
    main()
