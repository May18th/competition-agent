# -*- coding: utf-8 -*-
"""科创赛事助手 · 常驻守护进程（无需管理员权限）

不用管理员提权，不依赖任何 shell 会话，自己一直活着：
  - 每 CHECK_INTERVAL 秒探一次 Flask（直连 socket，绕开系统代理）
  - 不通就清掉占端口的僵尸进程，再用 pythonw 无窗口拉起
  - cpolar 是 Windows 服务，系统自己会重连，这里只顺带把最新公网地址写进「公网地址.txt」

自身由注册表 Run 键开机自启。也可以手工运行（幂等：发现已有守护在跑就退出）。
"""
import os
import re
import socket
import subprocess
import sys
import time

CHECK_INTERVAL = 20          # 探活间隔（秒）
STARTUP_WAIT = 25            # 拉起后最多等它多久

PYW = r'C:\Users\34984\.conda\envs\rag-dev\pythonw.exe'
PY = r'C:\Users\34984\.conda\envs\rag-dev\python.exe'
PROJECT_DIR = r'C:\Users\34984\Doubao\chats\2026-09-23\new-chat\科创赛事助手'
CPOLAR_LOG_DIR = r'C:\Users\34984\.cpolar\logs'
PUBLIC_URL_FILE = os.path.join(PROJECT_DIR, '公网地址.txt')
GUARDIAN_LOG = os.path.join(PROJECT_DIR, 'guardian.log')

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
DETACH = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def write_log(msg):
    line = '[%s] %s' % (time.strftime('%m-%d %H:%M:%S'), msg)
    try:
        with open(GUARDIAN_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def http_ok(host, port, timeout=5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.sendall(('GET / HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n' % host).encode())
        head = s.recv(300)
        first = head.split(b'\r\n')[0]
        return b'200' in first
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def port_pid(port):
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


LOCK_FILE = os.path.join(os.environ.get('TEMP', r'C:\Windows\Temp'),
                         'kechuang_watcher.lock')


def _pid_alive(pid):
    """Windows 下 os.kill(pid, 0) 不可用，用 tasklist 判断进程是否还在"""
    try:
        out = subprocess.run(['tasklist', '/NH', '/FI', 'PID eq %d' % pid],
                             capture_output=True, text=True,
                             encoding='utf-8', errors='ignore').stdout
        return str(pid) in out
    except Exception:
        return False


def _lock_taken_by_other():
    """文件锁兜底：wmic 在本机不存在，already_running() 会恒返回 False，
    导致计划任务每 5 分钟起一个新的守护进程、重复拉起 Flask 抢占 8080。
    这里用独占文件锁做第二道判断，持有者还活着就认为自己该退出。"""
    me = os.getpid()
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(me).encode())
        return False, fd
    except FileExistsError:
        pass
    except Exception:
        return False, None
    try:
        with open(LOCK_FILE, encoding='utf-8', errors='ignore') as f:
            pid = int((f.read().strip() or '0'))
    except Exception:
        pid = 0
    if pid and pid != me and _pid_alive(pid):
        return True, None                      # 别人持有 → 本进程退出
    try:
        os.remove(LOCK_FILE)                   # 陈旧锁，回收
    except Exception:
        pass
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(me).encode())
    except Exception:
        return False, None
    return False, fd


def already_running():
    """避免重复守护：看有没有别的进程命令行含 _watcher.py。
    计划任务每 5 分钟会触发一次，靠这个判断确保始终只有一个在跑。
    python.exe 和 pythonw.exe 都要查（可能因启动方式不同而不同）。

    本机没有 wmic，wmic 分支会抛异常被吞掉并恒返回 False，
    所以必须再走一遍文件锁兜底。
    """
    me = os.getpid()
    n = 0
    for proc in ('python.exe', 'pythonw.exe'):
        try:
            out = subprocess.run(
                ['wmic', 'PROCESS', 'WHERE', 'name="%s"' % proc, 'GET', 'ProcessId,CommandLine', '/VALUE'],
                capture_output=True, text=True, encoding='utf-8', errors='ignore').stdout
            for b in out.replace('\r', '').split('\n\n'):
                if '_watcher.py' in b:
                    m = re.search(r'ProcessId=(\d+)', b)
                    if m and int(m.group(1)) != me:
                        n += 1
        except Exception:
            pass
    if n > 0:
        return True
    taken, _ = _lock_taken_by_other()
    return taken


def fetch_public_url():
    today = time.strftime('%Y%m%d')
    best = None
    pat = re.compile(r'https?://[A-Za-z0-9.-]+\.(?:cpolar\.(?:cn|top|io)|vip\.cpolar\.cn)')
    try:
        for fn in os.listdir(CPOLAR_LOG_DIR):
            # 注意：日志文件名形如 cpolar_service.log.20260925，以日期结尾而非 .log，
            # 不能再用 endswith('.log') 过滤，否则永远筛不中。
            if today not in fn or fn.endswith('.zip'):
                continue
            p = os.path.join(CPOLAR_LOG_DIR, fn)
            if not os.path.isfile(p):
                continue
            try:
                txt = open(p, encoding='utf-8', errors='ignore').read()
            except Exception:
                continue
            for m in pat.finditer(txt):
                cand = m.group(0)
                # 只取 http 地址（website 隧道是 http；remoteDesktop 是 tcp:// 不会被本正则匹配）
                # 取最后出现的 http 地址 = 最新隧道地址（免费版地址会变，r16.cpolar.top 也可能是 website）
                if cand.startswith('http://'):
                    best = cand
    except Exception as e:
        write_log('读 cpolar 日志失败: %r' % e)
    return best


def update_url(url):
    if url is None:
        return
    # cpolar 免费版 https 证书不稳定（SSL 会失败），直接用 http 地址即可访问
    final = url if url.startswith('http://') else url.replace('https://', 'http://')
    try:
        with open(PUBLIC_URL_FILE, 'w', encoding='utf-8') as f:
            f.write('# 科创赛事助手 · 公网访问地址\n')
            f.write('# 最后更新：%s\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
            f.write('# 本文件由 _watcher.py 每 20 秒自动更新，地址变了以这里为准。\n\n')
            f.write(final + '\n')
    except Exception:
        pass


def start_flask():
    try:
        subprocess.Popen([PYW, 'run.py'], cwd=PROJECT_DIR, creationflags=DETACH,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
        return True
    except Exception as e:
        write_log('Flask 拉起失败: %r' % e)
        return False


def main():
    write_log('守护进程启动 PID=%d，间隔 %d 秒' % (os.getpid(), CHECK_INTERVAL))
    down_since = None
    while True:
        try:
            if http_ok('127.0.0.1', 8080):
                if down_since:
                    write_log('Flask 已恢复正常')
                    down_since = None
            else:
                if down_since is None:
                    down_since = time.time()
                    write_log('Flask 无响应，清理占端口的僵尸进程...')
                    for pid in port_pid(8080):
                        write_log('  终止僵尸 PID %s' % pid)
                        kill_pid(pid)
                    time.sleep(2)
                    write_log('拉起 Flask...')
                    if start_flask():
                        ok = False
                        for _ in range(STARTUP_WAIT):
                            time.sleep(1)
                            if http_ok('127.0.0.1', 8080):
                                ok = True
                                break
                        if ok:
                            write_log('Flask 已恢复 ✔')
                            down_since = None
                        else:
                            write_log('Flask 拉起后 %d 秒仍无响应，下轮重试' % STARTUP_WAIT)
            update_url(fetch_public_url())
            # 需要让守护顺便帮你重建内网穿透就解开下面两行的注释
            # （默认不动 cpolar：它是 Windows 服务，系统自己会重连，而且 sc 命令要管理员权限）
            # subprocess.run(['D:\\cpolar', 'http', '8080', '-log=stdout'],
            #                creationflags=DETACH, cwd=PROJECT_DIR)
        except Exception as e:
            write_log('守护循环异常: %r' % e)
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    if already_running():
        write_log('已有守护进程在跑，本次退出（PID=%d）' % os.getpid())
        sys.exit(0)
    main()
