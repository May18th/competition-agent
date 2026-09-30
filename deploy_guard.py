#!/usr/bin/env python3
"""部署守卫（安全版，替代原 deploy_guard.py）

与旧版的唯一本质区别：旧版第②步直接 `git reset --hard origin/main`，
会**静默抹掉所有未提交的改动**（index.html / static/ 等前端根本不在备份列表里），
这就是 2026-09-30 凌晨「04:52 全站掉线」事故的根因。

安全版流程：
  ① 备份 py + 前端(index.html / static/) 到时间戳目录
    ② 若工作树有未提交改动 → 先 `git stash push` 保护「已跟踪」的改动
       （注意：不用 -u。reset --hard 本就不删未跟踪文件，.venv/ 等大型未跟踪目录
        绝不能被塞进 stash，否则既慢又容易在 pop 时出错）
    ③ git fetch + reset --hard origin/main（此时工作树已干净，reset 不再丢东西）
  ④ py_compile 校验 → systemctl reload → sleep 5 → health 校验
  ⑤ 部署成功或失败回滚后，都执行 `git stash pop` 把部署前的未提交改动还原回去
任一步失败 → 自动恢复 py 备份 + 还原前端 + reload + 输出原因；
未提交改动始终优先保护，绝不被 reset 吃掉。

用法（在服务器 /opt/comp-agent 下）：
    .venv/bin/python deploy_guard.safe.py
    或  python3 deploy_guard.safe.py
紧急强制重置（放弃未提交改动，慎用）：
    .venv/bin/python deploy_guard.safe.py --force-reset
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
# 前端资源也纳入备份/回滚，旧版漏了这里才导致事故
FRONTEND_FILES = ["index.html"]
FRONTEND_DIRS = ["static"]
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
    """把 py 文件 + 前端(index.html / static/) 全量备份到时间戳目录。"""
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    made = []  # (src, dst) 用于回滚 py / index.html
    for f in PY_FILES + FRONTEND_FILES:
        p = os.path.join(REPO, f)
        if os.path.exists(p):
            dst = p + ".bak_" + ts
            shutil.copy2(p, dst)
            made.append((p, dst))
    # static/ 目录整体备份
    static_bak = None
    for d in FRONTEND_DIRS:
        src = os.path.join(REPO, d)
        if os.path.isdir(src):
            dst = os.path.join(REPO, d + ".bak_" + ts)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            static_bak = (src, dst)
    return made, static_bak, ts


def rollback(backups, static_bak):
    """把 py / index.html 备份还原回去，再还原 static/ 目录，最后 reload。"""
    for src, dst in backups:
        try:
            shutil.copy2(dst, src)
        except Exception:
            pass
    if static_bak:
        src, dst = static_bak
        try:
            if os.path.exists(src):
                shutil.rmtree(src)
            shutil.copytree(dst, src)
        except Exception:
            pass
    code, _, _ = run("systemctl reload comp-agent")
    if code != 0:
        run("systemctl restart comp-agent")


def restore_stash(stash_created):
    """部署结束（无论成败）都尝试把未提交改动还原回去。"""
    if not stash_created:
        return
    code, out, err = run(f"cd {REPO} && git stash pop")
    if code == 0:
        print("[guard] ✅ 已恢复部署前的未提交改动（git stash pop 成功）")
    else:
        ref = run(f"cd {REPO} && git rev-parse stash@{{0}}")[1].strip()
        print(f"[guard] ⚠️ stash pop 冲突/失败：未提交改动已安全保留在 stash（{ref or 'stash@{0}'}），"
              f"请手动 `git stash pop` 解决冲突后再部署。stderr={err}")


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
    force_reset = "--force-reset" in sys.argv

    print("[guard] ① 备份 py + 前端(index.html / static/)")
    backups, static_bak, ts = backup()
    if not backups:
        print("[guard] 无现有文件可备份（首次部署），继续")

    # ② 保护未提交改动：先 stash（含未跟踪 -u），再 reset
    code, out, _ = run(f"cd {REPO} && git status --porcelain")
    dirty = bool(out.strip())
    stash_created = False

    if force_reset:
        if dirty:
            print("[guard] ⚠️ --force-reset：将丢弃全部未提交改动（含前端）")
        code, out, err = run(f"cd {REPO} && git fetch origin main")
        if code != 0:
            print(f"[guard] ❌ git fetch 失败：{err}")
            return 1
        code, _, err = run(f"cd {REPO} && git reset --hard origin/main")
        if code != 0:
            print(f"[guard] ❌ git reset 失败：{err}")
            rollback(backups, static_bak)
            return 1
    else:
        if dirty:
            print("[guard] ⚠️ 检测到未提交改动，先 git stash 保护已跟踪改动（未跟踪文件 reset --hard 不动）")
            code, out, err = run(f"cd {REPO} && git stash push -m 'deploy_guard auto-stash {ts}'")
            if code != 0:
                print(f"[guard] ❌ stash 失败，中止部署以免丢失改动：{err}")
                return 1
            stash_created = True
        else:
            print("[guard] 工作树干净，无需 stash")

        print("[guard] ② git fetch + reset --hard origin/main（改动已在 stash 中保护）")
        code, out, err = run(f"cd {REPO} && git fetch origin main")
        if code != 0:
            print(f"[guard] ❌ git fetch 失败：{err}")
            restore_stash(stash_created)
            return 1
        code, out, err = run(f"cd {REPO} && git reset --hard origin/main")
        if code != 0:
            print(f"[guard] ❌ git reset 失败：{err}")
            rollback(backups, static_bak)
            restore_stash(stash_created)
            return 1

    print("[guard] ③ py_compile 校验全部 py")
    ok, err = validate()
    if not ok:
        print("[guard] ❌ 校验未通过，自动回滚")
        rollback(backups, static_bak)
        restore_stash(stash_created)
        print(err)
        return 1

    print("[guard] ④ systemctl reload（平滑重启）")
    code, _, err = run("systemctl reload comp-agent")
    if code != 0:
        code, _, err = run("systemctl restart comp-agent")
        if code != 0:
            print(f"[guard] ❌ 重启失败：{err}")
            rollback(backups, static_bak)
            restore_stash(stash_created)
            return 1

    print("[guard] ⑤ sleep 5 后 health 校验")
    time.sleep(5)
    if not health_ok():
        print("[guard] ❌ health 校验失败，自动回滚")
        rollback(backups, static_bak)
        restore_stash(stash_created)
        return 1

    print(f"[guard] ✅ 部署成功（备份时间戳 {ts}，可回滚）")
    restore_stash(stash_created)
    return 0


if __name__ == "__main__":
    sys.exit(main())
