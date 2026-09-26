# -*- coding: utf-8 -*-
"""
从后端 data/*.txt 知识库解析出结构化索引 static/competition_index.json，
供前端「选赛事→瞬间显示官方资料」使用（一次拉取 + 本地缓存，0 延迟匹配）。

知识库格式（后端约定）：
    # 标题
    ## 比赛介绍
    ## 评分标准          (n)名称：百分比%   |  或 markdown 表格 | 维度 | 权重 | ... |
    ## 申报书章节        (n)章节名
    ## 偏好方向          (n)...
    ## 常见扣分点        ...

已知变体：
- RoboMaster 有两个「## 评分标准」，第二个其实是章节（不带 %），需自动归位
- 蓝桥杯用 markdown 表格写评分标准
- 国创 / 小挑 没有「常见扣分点」
"""
import os, re, json, glob

# 用脚本自身位置反推仓库根目录，换机器也能直接跑
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
OUT = os.path.join(REPO, "static", "competition_index.json")

# 下拉里的赛名 → 知识库文件名（key）。用于前端本地匹配，保证选哪个都能命中。
ALIAS = {
    "iCAN": ["iCAN大学生创新创业大赛", "ican", "ican大赛"],
    "互联网+": ["中国国际互联网+大学生创新创业大赛", "中国国际大学生创新大赛", "互联网加大赛"],
    "挑战杯": ["挑战杯全国大学生课外学术科技作品竞赛", "大挑", "挑战杯大挑"],
    "小挑": ["挑战杯中国大学生创业计划竞赛（小挑）", "挑战杯中国大学生创业计划竞赛", "小挑"],
    "国创": ["国家级大学生创新创业训练计划", "全国大学生创新创业训练计划", "大创"],
    "数学建模": ["全国大学生数学建模竞赛", "数学建模竞赛"],
    "电子设计": ["全国大学生电子设计竞赛", "电子设计竞赛"],
    "蓝桥杯": ["蓝桥杯全国软件和信息技术专业人才大赛", "蓝桥杯"],
    "计算机设计": ["中国大学生计算机设计大赛"],
    "广告艺术": ["全国大学生广告艺术大赛", "大广赛"],
    "服务外包": ["中国大学生服务外包创新创业大赛"],
    "信息安全": ["全国大学生信息安全竞赛"],
    "西门子杯": ["西门子杯中国智能制造挑战赛"],
    "RoboMaster": ["RoboMaster全国大学生机器人大赛", "机甲大师", "robomaster"],
    "金砖": ["一带一路暨金砖国家技能发展与技术创新大赛（青年创客大赛）",
             "金砖国家技能发展与技术创新大赛", "金砖大赛"],
}

# 文档类型：按文件名直接指定，比从介绍里猜可靠
DOC_TYPE_MAP = {
    "iCAN": "作品说明书",
    "互联网+": "商业计划书",
    "小挑": "商业计划书",
    "服务外包": "商业计划书",
    "挑战杯": "申报书",
    "信息安全": "申报书",
    "国创": "结题报告",
    "数学建模": "论文",
    "电子设计": "设计报告",
    "蓝桥杯": "申报书",
    "计算机设计": "申报书",
    "广告艺术": "申报书",
    "西门子杯": "方案设计书",
    "RoboMaster": "技术方案书",
    "金砖": "申报书",
}

# 文档类型：能推断就推断，推断不出留给前端兜底
DOC_TYPE_HINT = [
    ("作品说明书", "作品说明书"),
    ("商业计划书", "商业计划书"),
    ("创业计划书", "商业计划书"),
    ("学术论文", "申报书"),
    ("调查报告", "申报书"),
    ("科技发明", "申报书"),
    ("研究报告", "研究报告"),
]

RE_PCT = re.compile(r"^[(\[]?\s*\d+\s*[)\].、]?\s*(.+?)\s*[：:]\s*(\d+(?:\.\d+)?)\s*%")
RE_ITEM = re.compile(r"^[(\[]?\s*\d+\s*[)\].、]?\s*(.+)$")
RE_DASH = re.compile(r"^[-*]\s*(.+)$")


def split_sections(text):
    """按 ## 切成 {标题: 内容行列表}，重复标题合并"""
    blocks, cur, buf = [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur is not None:
                blocks.append((cur, buf))
            cur, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if cur is not None:
        blocks.append((cur, buf))
    merged = {}
    for title, lines in blocks:
        merged.setdefault(title, [])
        merged[title].extend(lines)
    return merged


def clean_items(lines):
    """把 (1)xxx / - xxx 抽成纯文本列表，去掉表格分隔行和空行"""
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("|---") or set(s) <= set("|-: "):
            continue
        m = RE_PCT.match(s) or RE_ITEM.match(s) or RE_DASH.match(s)
        out.append(m.group(1).strip() if m else s)
    return out


def parse_scoring(lines):
    """
    评分标准：优先 (n)名称：xx%；其次 markdown 表格。
    返回 (评分项, 认不出来的行) —— 后者多半是写错标题的章节
    （RoboMaster 有两个「## 评分标准」，第二个其实列的是申报书章节）
    """
    items, orphans = [], []
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("|---") or set(s) <= set("|-: "):
            continue
        # 表格行：| 维度 | 权重 | 说明 |
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 2 and re.search(r"\d+\s*%", cells[1]):
                name = cells[0].strip("* ").strip()
                if name and name not in ("维度", "---"):
                    pct = re.search(r"(\d+(?:\.\d+)?)", cells[1])
                    if pct:
                        items.append([name, int(float(pct.group(1)))])
                        continue
            # 表头/说明行不算 orphan
            if not (cells and cells[0] in ("维度",)):
                orphans.append(" ".join(cells).strip("* ").strip())
            continue
        # 说明性文字（如蓝桥杯「说明：官方以OJ评测…」）不是章节，丢掉
        if s.startswith("说明") or s.startswith("注：") or s.startswith("注:"):
            continue
        m = RE_PCT.match(s)
        if m:
            items.append([m.group(1).strip(), int(float(m.group(2)))])
        else:
            t = RE_ITEM.match(s) or RE_DASH.match(s)
            orphans.append(t.group(1).strip() if t else s)
    return items, orphans


def guess_doc_type(key, title, intro):
    if key in DOC_TYPE_MAP:
        return DOC_TYPE_MAP[key]
    blob = (title or "") + " " + (intro or "")
    for kw, dt in DOC_TYPE_HINT:
        if kw in blob:
            return dt
    return ""


def is_real_section(s):
    """
    判断一条内容是不是真的「章节标题」。
    知识库里有些块标题写着「申报书章节」，内容却是一整句说明
    （例：iCAN 写的是「创新赛道：双盲评审，侧重原创原型，不强制商业化…」）。
    这种不能当章节显示给学生——他会照着写成章节名。
    章节标题的特征：短、没有句号分号、不是一句完整的话。
    """
    if not s:
        return False
    if len(s) > 26:
        return False
    for bad in ("。", "；", "，", "："):
        if bad in s:
            return False
    return True


def main():
    items = []
    for path in sorted(glob.glob(os.path.join(DATA, "*.txt"))):
        key = os.path.basename(path).replace(".txt", "")
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        sec = split_sections(raw)

        title = ""
        for ln in raw.splitlines():
            if ln.startswith("# "):
                title = ln[2:].strip()
                break

        intro = " ".join(x.strip() for x in sec.get("比赛介绍", []) if x.strip()).strip()

        scoring, orphan = parse_scoring(sec.get("评分标准", []))
        sections = clean_items(sec.get("申报书章节", []))
        # 认不出来的行多半是写错标题的章节（RoboMaster），放到章节前面
        if orphan:
            sections = orphan + sections
        # 丢掉明显是整句的条目：知识库里 iCAN / 国创 的「申报书章节」块
        # 实际写的是赛道说明、结题要求，直接显示会让学生把一整句当章节名
        sections = [s for s in sections if is_real_section(s)]

        pref = clean_items(sec.get("偏好方向", []))
        deduct = " ".join(x.strip() for x in sec.get("常见扣分点", []) if x.strip()).strip()

        keys = [key, title.replace('"', "").strip()] + ALIAS.get(key, [])
        keys = list(dict.fromkeys([k for k in keys if k]))

        items.append({
            "key": key,
            "title": title,
            "keys": keys,
            "intro": intro,
            "doc_type": guess_doc_type(key, title, intro),
            "scoring": scoring,
            "sections": sections,
            "preference": pref,
            "deduct": deduct,
            "chars": len(raw),
            # 资料缺口：知识库里确实缺的项（iCAN/国创 的章节块内容是错的，已过滤成空）
            # 前端据此提示「该赛事官方资料待补充」，而不是把错的内容当权威显示
            "gaps": ([] if scoring else ["评分标准"]) +
                    ([] if sections else ["章节要求"]) +
                    ([] if deduct else ["常见扣分点"]),
        })

    data = {
        "version": "2026-09-26",
        "source": "由 data/*.txt 解析生成（后端知识库）",
        "count": len(items),
        "items": items,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("生成 %s（%d 个赛事）\n" % (OUT, len(items)))
    for it in items:
        print("%-12s 评分%d项 章节%d项 扣分点:%s 文档:%s" % (
            it["key"], len(it["scoring"]), len(it["sections"]),
            "有" if it["deduct"] else "无", it["doc_type"] or "(待定)"))


if __name__ == "__main__":
    main()
