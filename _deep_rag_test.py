# -*- coding: utf-8 -*-
"""深度版 + 关键词 RAG 联调验证。

验证三件事：
1. 深度版带关键词能正常跑完（此前只测过 fast 版）
2. 范文注入是否真的影响输出（查特征词命中）
3. 注入 3 篇范文后，逐字流式有没有被拖慢（对比基线：增长 16 次 / 57-82s）

用法：python _deep_rag_test.py
结果写入 _deep_rag_result.json
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8080"
OUT = "_deep_rag_result.json"

# 新演示选题：非遗 + AI + 商业闭环，三个维度都能展开
IDEA = ("做苏绣非遗纹样的数字化保护与文创设计平台：手机拍照采集绣品纹样，"
        "AI 自动矢量化提取结构并建立纹样基因库，设计师可一键生成文创设计稿，"
        "平台对接本地绣娘接单生产，帮助非遗传承人增收。")
KEYWORDS = "非遗, 人工智能, web网站, 初创阶段, 4人团队"


def post(path, payload, timeout=60):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def getj(path, timeout=60):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=timeout).read())


def main():
    t0 = time.time()
    r = post("/api/generate_async", {
        "competition_name": "挑战杯",
        "idea": IDEA,
        "proposal_draft": "",
        "mode": "deep",
        "keywords": KEYWORDS,
        "theme": None,
    })
    tid = r["task_id"]
    print("任务启动: %s" % tid)

    grows = {"proposal": [], "proposal_outline": []}
    first_seen = {}
    last = {"proposal": 0, "proposal_outline": 0}

    while time.time() - t0 < 600:
        time.sleep(1.5)
        s = getj("/api/status/" + tid)
        if s.get("status") != "running":
            break
        p = s.get("partial") or {}
        for k, v in p.items():
            if k not in first_seen:
                first_seen[k] = time.time() - t0
        for k in grows:
            if k in p and len(p[k]) != last[k]:
                last[k] = len(p[k])
                grows[k].append((round(time.time() - t0, 1), len(p[k])))

    st = getj("/api/status/" + tid)
    elapsed = time.time() - t0
    data = st.get("data") or {}
    prop = data.get("proposal") or ""

    # 范文风格特征词（种子范文里特有的数据化表述）
    marks = ["问卷", "试点", "留存", "百分点", "%", "人均", "覆盖",
             "转化", "准确率", "注册", "付费", "阶段"]
    hits = [m for m in marks if m in prop]

    result = {
        "task_id": tid,
        "status": st.get("status"),
        "error": st.get("error"),
        "elapsed_sec": round(elapsed, 1),
        "keywords": KEYWORDS,
        "idea": IDEA,
        "proposal_chars": len(prop),
        "proposal_chapters": prop.count("\n## ") + 1 if prop else 0,
        "outline_chars": len(data.get("proposal_outline") or ""),
        "ppt_chars": len(data.get("ppt_outline") or ""),
        "defense_chars": len(data.get("defense_questions") or ""),
        "has_rich_deck": bool((data.get("rich_deck") or {}).get("slides")),
        "selfcheck": data.get("proposal_selfcheck", ""),
        "style_hits": hits,
        "proposal_grow_times": len(grows["proposal"]),
        "outline_grow_times": len(grows["proposal_outline"]),
        "proposal_grow_span": (
            [grows["proposal"][0][0], grows["proposal"][-1][0]]
            if grows["proposal"] else None),
        "first_seen": {k: round(v, 1) for k, v in sorted(
            first_seen.items(), key=lambda x: x[1])},
        "head": prop[:300],
    }
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n=== 深度版 + RAG 联调结果 ===")
    print("状态: %s | 耗时 %.0fs" % (result["status"], elapsed))
    print("正文 %d 字 / %d 章 | 纲要 %d 字 | PPT %d 字 | 答辩 %d 字" % (
        result["proposal_chars"], result["proposal_chapters"],
        result["outline_chars"], result["ppt_chars"], result["defense_chars"]))
    print("逐字流式: proposal 增长 %d 次，区间 %s（基线 16 次 / 57-82s）" % (
        result["proposal_grow_times"], result["proposal_grow_span"]))
    print("PPT deck 可用: %s" % result["has_rich_deck"])
    print("范文风格特征词命中(%d): %s" % (len(hits), hits))
    print("\n--- 正文前 300 字 ---")
    print(prop[:300])
    print("\n结果已写入 %s" % OUT)


if __name__ == "__main__":
    main()
