#!/usr/bin/env python3
"""部署守卫（第九十六轮）：统一部署入口，防止代码级故障（NameError/语法错）把服务打挂。

流程：备份当前 py → git fetch + reset --hard origin/main → py_compile 校验 →
systemctl reload 平滑重启 → sleep 5 → curl /api/health 验证 status=ok。
任一步失败 → 自动恢复备份 + reload + 输出错误原因。

用法（在服务器 /opt/comp-agent 下）：
    .venv/bin/python deploy_guard.py
    或  python3 deploy_guard.py
"""
import os
import sys
import time
import shutil
import subprocess
import datetime

REPO = os.path.dirname(os.path.abspath(__file__))
PY_FILES = [
    "app.py", "competition_agents.py", "rich_pipeline.py",
    "docx_render.py", "pdf_render.py", "pptx_builder.py",
    "kb_distill.py", "kb_samples.py", "stage_reporter.py",
]
HEALTH_URL = "http://127.0.0.1:8080/api/health"
PYTHON = os.path.join(REPO, ".venv", "bin", "python")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable


def run(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, "", "命令超时"


def backup():
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    made = []
    for f in PY_FILES:
        p = os.path.join(REPO, f)
        if os.path.exists(p):
            dst = p + ".bak_" + ts
            shutil.copy2(p, dst)
            made.append((p, dst))
    return made, ts


def rollback(backups):
    """把备份文件还原回去（覆盖当前 py），再做一次 reload。"""
    for src, dst in backups:
        try:
            shutil.copy2(dst, src)
        except Exception:
            pass
    code, _, _ = run("systemctl reload comp-agent")
    if code != 0:
        run("systemctl restart comp-agent")


def validate():
    for f in PY_FILES:
        p = os.path.join(REPO, f)
        if not os.path.exists(p):
            continue
        code, out, err = run(f"cd {REPO} && {PYTHON} -m py_compile {f}")
        if code != 0:
            return False, f"py_compile 校验失败: {f}\n{err or out}"
    return True, ""


def health_ok():
    code, out, _ = run(f"curl -s -m 10 {HEALTH_URL}")
    return code == 0 and '"status"' in out and '"ok"' in out


def main():
    print("[guard] ① 备份当前 py")
    backups, ts = backup()
    if not backups:
        print("[guard] 无现有 py 可备份（首次部署），继续")

    print("[guard] ② git fetch + reset --hard origin/main")
    code, out, err = run(f"cd {REPO} && git fetch origin main")
    if code != 0:
        print(f"[guard] ❌ git fetch 失败：{err}")
        return 1
    code, out, err = run(f"cd {REPO} && git reset --hard origin/main")
    if code != 0:
        print(f"[guard] ❌ git reset 失败：{err}")
        rollback(backups)
        return 1

    print("[guard] ③ py_compile 校验全部 py")
    ok, err = validate()
    if not ok:
        print(f"[guard] ❌ 校验未通过，自动回滚")
        rollback(backups)
        print(err)
        return 1

    print("[guard] ④ systemctl reload（平滑重启）")
    code, _, err = run("systemctl reload comp-agent")
    if code != 0:
        code, _, err = run("systemctl restart comp-agent")
        if code != 0:
            print(f"[guard] ❌ 重启失败：{err}")
            rollback(backups)
            return 1

    print("[guard] ⑤ sleep 5 后 health 校验")
    time.sleep(5)
    if not health_ok():
        print("[guard] ❌ health 校验失败，自动回滚")
        rollback(backups)
        return 1

    print(f"[guard] ✅ 部署成功（备份时间戳 {ts}，可回滚）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
