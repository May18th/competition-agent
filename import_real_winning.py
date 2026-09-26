# -*- coding: utf-8 -*-
"""导入真实获奖项目参考样本到范文库。

用法：
    python import_real_winning.py

来源：knowledge_base/real_winning_samples.json，全部为公开获奖报道归纳，
非完整申报书原文；type 显式写「范文」、score=90，绕过启发式打分。
幂等：按内容哈希去重，可重复执行。
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(BASE, "knowledge_base", "real_winning_samples.json")


def main():
    if not os.path.exists(SEED):
        print("未找到种子文件：%s" % SEED)
        return 1
    with open(SEED, encoding="utf-8") as f:
        items = json.load(f)

    import kb_samples as k
    added, skipped = 0, 0
    for it in items:
        content = (it.get("content") or "").strip()
        tags = it.get("tags") or []
        if not content or not tags:
            print("  [跳过] 内容或标签为空")
            continue
        sid, is_new = k.add_sample(
            content, tags,
            source=it.get("source", ""),
            score=int(it.get("score", 90)),
            type="范文",
            summary="",
        )
        if is_new:
            added += 1
        else:
            skipped += 1

    print("真实获奖参考样本导入完成：新增 %d / 跳过(已存在) %d" % (added, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
