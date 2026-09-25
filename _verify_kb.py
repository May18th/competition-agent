# -*- coding: utf-8 -*-
"""范文库 RAG 改造验收脚本（任务 1-6 交付后一键自测）

用法：
    python _verify_kb.py            # 只测数据层 + 检索层（不需要启动服务）
    python _verify_kb.py --api      # 额外测接口层（需要 8080 服务已启动）

退出码 0 = 全部通过，1 = 有失败项。
"""
import os
import sys
import json

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print("  %-4s %-38s %s" % ("PASS" if ok else "FAIL", name, detail))
    return ok


def phase1_data():
    print("\n[1] 数据层 kb_samples.py")
    try:
        import kb_samples as k
    except Exception as e:
        return check("模块可导入", False, str(e))
    check("模块可导入", True)

    sid = k.add_sample("【验收用范文】本项目为文旅数字化Web平台，4人学生团队开发，"
                       "已完成原型并在1所高校试点，累计用户300人。",
                       ["项目简介", "文化文旅", "web网站", "4人团队"])
    check("add_sample 返回 id", isinstance(sid, int) and sid > 0, "id=%s" % sid)

    items = k.list_samples()
    check("list_samples 有数据", len(items) > 0, "%d 条" % len(items))

    hit = [x for x in items if x.get("id") == sid]
    check("新增记录可查回", bool(hit),
          "tags=%s" % (hit[0].get("tags") if hit else ""))

    tags = k.get_all_tags()
    ok = isinstance(tags, dict) and "module" in tags
    check("get_all_tags 返回三类词表", ok,
          "module %d / track %d / feature %d" % (
              len(tags.get("module", [])), len(tags.get("track", [])),
              len(tags.get("feature", []))) if ok else "")

    check("delete_sample 生效", k.delete_sample(sid))
    return sid


def phase2_retrieve():
    print("\n[2] 检索层 kb_retrieve.py")
    try:
        from kb_retrieve import extract_keywords, search_samples
    except Exception as e:
        return check("模块可导入", False, str(e))
    check("模块可导入", True)

    ks = extract_keywords("我做了一个苏轼文旅网站，4人学生团队，要写项目简介")
    need = ["文化文旅", "web网站", "项目简介"]
    got = [n for n in need if n in ks]
    check("关键词抽取命中预期标签", len(got) >= 2,
          "抽出=%s（期望含 %s）" % (ks, need))

    alias = extract_keywords("我们用了AI和机器学习做网页")
    check("别名识别（AI/网页）",
          ("人工智能" in alias) or ("web网站" in alias), "抽出=%s" % alias)

    ref = search_samples(ks, "项目简介")
    check("search_samples 有命中", bool(ref and ref.strip()),
          "%d 字" % len(ref or ""))

    check("命中长度封顶 3000", len(ref or "") <= 3000, "%d 字" % len(ref or ""))

    empty = search_samples(["不存在的关键词zzz"], "项目简介")
    check("无命中时返回空不报错", empty == "" or empty is None)
    return True


def phase3_inject():
    print("\n[3] 注入层 competition_agents.py")
    try:
        import competition_agents as ca
    except Exception as e:
        return check("模块可导入", False, str(e))

    check("存在 _ref_block 函数", hasattr(ca, "_ref_block"))
    if not hasattr(ca, "_ref_block"):
        return False

    st = {"idea": "苏轼文旅网站", "user_keywords": "文化文旅,web网站",
          "competition_name": "挑战杯"}
    try:
        blk = ca._ref_block(st, "项目简介")
        check("_ref_block 可调用且不抛异常", True,
              "返回 %d 字" % len(blk or ""))
    except Exception as e:
        return check("_ref_block 可调用且不抛异常", False, str(e))

    try:
        bad = ca._ref_block({}, "项目简介")
        check("空 state 降级不崩溃", True)
    except Exception as e:
        check("空 state 降级不崩溃", False, str(e))

    src = open("competition_agents.py", encoding="utf-8").read()
    check("_stream_llm 未被破坏", "_stream_llm" in src and "def _stream_llm" in src)
    return True


def phase6_seed():
    print("\n[6] 种子数据")
    p = os.path.join(BASE, "knowledge_base", "seed_samples.json")
    if not os.path.exists(p):
        return check("seed_samples.json 存在", False, "未找到")
    try:
        data = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        return check("seed_samples.json 可解析", False, str(e))
    check("seed_samples.json 可解析", True, "%d 段" % len(data))
    mods = set()
    for it in data:
        mods.update([t for t in it.get("tags", []) if t in
                     ["项目简介", "社会价值", "实践过程", "商业模式",
                      "创新点", "风险分析"]])
    check("覆盖 >=4 个模块标签", len(mods) >= 4, "已覆盖 %s" % sorted(mods))
    return True


def phase_api():
    print("\n[4] 接口层（需 8080 已启动）")
    import urllib.request
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = "http://127.0.0.1:8080"

    def post(path, body):
        r = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                   headers={"Content-Type": "application/json"})
        return json.loads(op.open(r, timeout=20).read())

    def getj(path):
        return json.loads(op.open(base + path, timeout=20).read())

    def delete_(path):
        r = urllib.request.Request(base + path, method="DELETE")
        return json.loads(op.open(r, timeout=20).read())

    try:
        h = getj("/api/health")
        check("/api/health", bool(h.get("success") or h.get("status")), str(h)[:60])
    except Exception as e:
        return check("/api/health", False, "服务未启动: %s" % e)

    try:
        t = getj("/api/kb/tags")
        check("GET /api/kb/tags", bool(t.get("module")), "module %d 个" % len(t.get("module", [])))
    except Exception as e:
        check("GET /api/kb/tags", False, str(e))

    try:
        r = post("/api/kb/add", {"content": "验收测试范文", "tags": ["项目简介"]})
        check("POST /api/kb/add", bool(r.get("success")), "id=%s" % r.get("id"))
        if r.get("id"):
            check("DELETE /api/kb/delete", bool(delete_("/api/kb/delete/%s" % r["id"])
                                                .get("success")))
    except Exception as e:
        check("POST /api/kb/add", False, str(e))

    try:
        l = getj("/api/kb/list")
        check("GET /api/kb/list", bool(l.get("success")),
              "%d 条" % len(l.get("items", [])))
    except Exception as e:
        check("GET /api/kb/list", False, str(e))
    return True


def main():
    print("=" * 70)
    print("范文库 RAG 改造验收")
    print("=" * 70)
    phase1_data()
    phase2_retrieve()
    phase3_inject()
    phase6_seed()
    if "--api" in sys.argv:
        phase_api()
    else:
        print("\n[4] 接口层 —— 跳过（加 --api 参数测，需先启动 8080）")

    bad = [n for n, ok, _ in results if not ok]
    print("\n" + "=" * 70)
    print("结果：%d 项通过 / %d 项失败" % (len(results) - len(bad), len(bad)))
    if bad:
        print("失败项：")
        for n in bad:
            print("   - %s" % n)
    print("=" * 70)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
