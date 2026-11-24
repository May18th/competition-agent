# -*- coding: utf-8 -*-
"""把「压缩保住创新点 + 压缩后复补」补到线上（app.py / competition_agents.py）。

背景：线上和本地是两套血缘，不能整文件覆盖，只能按符号逐处打补丁。
配套回归见 tests/test_backend.py::TestBlindLeakDetection 与 scorecard 补写用例。

用法：
    python tests/probes/_patch_online_innovation2.py --check    # 只检查基线符号
    python tests/probes/_patch_online_innovation2.py --apply    # 生成打好补丁的文件到 tmp_online/
然后 scp 覆盖 + 重启 comp-agent。

铁律：每次重新拉线上当前文件当基线，并断言关键符号计数（踩过一次用旧基线覆盖掉诊断路由）。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = os.path.join(ROOT, ".workbuddy", "tmp_online")

# ---------------- competition_agents.py（CRLF） ----------------
CA_OLD = ('                "3. 章节结构、标题（## 一、xxx）与序号必须保持不变，核心数字和技术名词保留；\\n"\n'
          '                "4. 中文标点用全角。\\n\\n"')
CA_NEW = ('                "3. 章节结构、标题（## 一、xxx）与序号必须保持不变，核心数字和技术名词保留；\\n"\n'
          '                "4. **若正文有以 ①②③ 编号列出的创新点或清单，整句原样保留，不得删除、不得改写成"\n'
          '                "叙述句**——这是评分点，删了要丢分；\\n"\n'
          '                "5. 中文标点用全角。\\n\\n"')

# ---------------- app.py（LF） ----------------
APP_A_OLD = ('    # 装在这里才能真正覆盖所有出口（writer / revise / 以后新增的任何节点）。\n'
             '    try:\n'
             '        _gate_mode = data.get("mode") or "fast"')
APP_A_NEW = ('    # 装在这里才能真正覆盖所有出口（writer / revise / 以后新增的任何节点）。\n'
             '    _gate_clipped = False\n'
             '    try:\n'
             '        _gate_mode = data.get("mode") or "fast"')

APP_B_OLD = ('                if _fixed:\n'
             '                    result["proposal"] = _fixed\n'
             '                    print(f"📏 最终篇幅闸门：')
APP_B_NEW = ('                if _fixed:\n'
             '                    result["proposal"] = _fixed\n'
             '                    _gate_clipped = True\n'
             '                    print(f"📏 最终篇幅闸门：')

APP_C_OLD = ('    except Exception as _e:\n'
             '        print(f"[final-length-gate] 跳过，保留原文：{_e}")\n')
APP_C_NEW = ('    except Exception as _e:\n'
             '        print(f"[final-length-gate] 跳过，保留原文：{_e}")\n'
             '\n'
             '    # 压缩后再兜一次创新点：压缩指令是「每章只留两句话」，编号列出的创新点经常被\n'
             '    # 一起砍掉（实测简洁版全文连「创新」二字都没有）。这里宁可超出上限百来字，\n'
             '    # 也不能丢掉占 16~30 分的创新点陈述；复检不升分会自动回退。\n'
             '    if _gate_clipped:\n'
             '        try:\n'
             '            _innov2 = _auto_patch_innovation(result, data)\n'
             '            if _innov2:\n'
             '                print(f"🧩 压缩后创新点复补：{_innov2}")\n'
             '        except Exception as _e:\n'
             '            print(f"[innovation-autopatch-2] 跳过，保留原文：{_e}")\n')


def _load(name):
    path = os.path.join(TMP, name)
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    return path, text, crlf


def _save(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def patch(name, pairs):
    path, text, crlf = _load(name)
    for i, (old, new) in enumerate(pairs, 1):
        n_old = text.count(old)
        if n_old != 1:
            print("  ✗ %s 第 %d 处锚点命中 %d 次（要求 1）" % (name, i, n_old))
            return False
        if text.count(new) > 0 and old != new:
            print("  ✗ %s 第 %d 处：补丁已经在，跳过以免重复插" % (name, i))
            return False
        text = text.replace(old, new, 1)
    _save(path, text, crlf)
    print("  ✓ %s 已打 %d 处（%s）" % (name, len(pairs), "CRLF" if crlf else "LF"))
    return True


def assert_syms(patched=False):
    """关键符号计数：确保补完没把别的功能搞丢。

    patched=False 是补丁前的基线期望，True 是补完后的期望。分开写死，
    免得「补丁没生效」和「补丁生效了」两种状态都能通过检查。
    """
    ok = True
    _, ca, _ = _load("competition_agents.py")
    _, app, _ = _load("app.py")
    checks = [
        ("competition_agents.py", ca, "_compress_to_length", 1, 1),
        ("competition_agents.py", ca, "①②③ 编号列出", 0, 1),
        ("app.py", app, "def _auto_patch_innovation", 1, 1),
        ("app.py", app, "_gate_clipped = True", 0, 1),
        ("app.py", app, "innovation-autopatch-2", 0, 1),
        ("app.py", app, "api/scorecard/patch", 1, 1),
        ("app.py", app, "def scorecard_patch_api", 1, 1),
        ("app.py", app, "_strip_cliches", 2, 2),
    ]
    for fname, text, sym, before, after in checks:
        want = after if patched else before
        got = text.count(sym)
        flag = "✓" if got == want else "✗"
        if got != want:
            ok = False
        print("  %s %s  %s=%d（期望 %d）" % (flag, fname, sym, got, want))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not os.path.isdir(TMP):
        print("缺基线目录：%s（先 scp 拉线上文件）" % TMP)
        return 2
    print("[before] 基线符号：")
    if not assert_syms():
        print("基线已不符预期，先重新拉线上文件再判断")
    if not args.apply:
        return 0
    print("[apply] 打补丁：")
    ok = patch("competition_agents.py", [(CA_OLD, CA_NEW)])
    ok = patch("app.py", [(APP_A_OLD, APP_A_NEW), (APP_B_OLD, APP_B_NEW), (APP_C_OLD, APP_C_NEW)]) and ok
    print("[after] 校验：")
    ok = assert_syms(patched=True) and ok
    print("结果：%s" % ("可部署" if ok else "有失败，别部署"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
