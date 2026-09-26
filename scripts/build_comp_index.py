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

# 赛道：只有知识库里真的写了赛道差异的赛事才配，其余一律不填（宁缺毋滥）。
# 字段来源严格区分：
#   desc / ban / ban_note  —— 来自 data/*.txt 官方原文，不要改写
#   focus / avoid / sections —— 由赛道定位推导的建议，_derived 标记为 True，前端需注明「建议」
TRACKS = {
    "iCAN": [
        {
            "key": "创新",
            "name": "创新赛道",
            "desc": "双盲评审，侧重原创原型，不强制商业化",
            # 官方原文只写「材料不能出现学校、导师信息」，这里照抄原文，
            # 不自行展开成「学院/专业/职称」等——展开版是我们推断的，不能当官方要求显示
            "ban": ["学校信息", "导师信息"],
            "ban_note": "双盲评审，材料里出现即直接扣分（官方扣分点第 4 条）",
            "focus": ["与现有方案的具体差异（说清差在哪，不说「更优」）",
                      "原型能跑、能现场演示，附实测数据",
                      "技术实现细节：用了什么方法、为什么这么选"],
            "avoid": ["商业融资计划", "市场空间预测", "盈利模式长篇论述"],
            "sections": ["项目背景与要解决的问题", "现有方案与不足",
                         "技术方案与创新点", "原型实现与测试结果",
                         "应用价值与落地场景", "不足与后续计划"],
        },
        {
            "key": "创业",
            "name": "创业赛道",
            "desc": "侧重商业落地、市场与盈利，适合已有订单试点项目",
            "ban": [],
            "ban_note": "",
            "focus": ["可核对的商业数据：试点单位、测试用户数、客单价、成本结构",
                      "已有订单或合作意向（写清哪一家、什么阶段）",
                      "与竞品的具体差异与壁垒"],
            "avoid": ["只有愿景没有数据的市场描述", "融资额、估值等无依据的数字"],
            "sections": ["项目概述与市场机会", "目标用户与需求验证",
                         "产品方案与核心壁垒", "商业模式与盈利路径",
                         "试点进展与真实数据", "团队与执行计划", "风险与应对"],
        },
        {
            "key": "挑战",
            "name": "挑战赛道",
            "desc": "企业联合命题专项赛道，含 AI 应用、机器人、电子信息等赛项；"
                    "创新 / 创业赛道可叠加报名挑战赛道",
            "ban": [],
            "ban_note": "",
            "focus": ["紧扣命题方的具体命题：命题是什么、你如何满足",
                      "对照命题要求的逐条响应（评委按命题完成情况打分）",
                      "原型针对命题场景的实测表现"],
            "avoid": ["脱离命题自说自话", "把通用方案换个名字当成命题应答"],
            "sections": ["命题理解与需求分析", "技术方案与命题对应",
                         "实现与测试验证", "命题指标达成情况",
                         "应用前景与迭代计划"],
        },
    ],
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


def norm_head(h):
    """
    标题归一化：去掉「（补充说明）」后缀。
    知识库里出现了 `## 评分标准（AI 应用挑战赛）`，精确匹配「评分标准」会失配，
    导致整块评分解析成 0 项——按归一化后的名字再匹配一次。
    """
    h = (h or "").strip()
    h = re.sub(r"[（(].*?[)）]\s*$", "", h).strip()
    return h


def sec_get(sec, name):
    """按归一化标题取块；同名多块（RoboMaster）内容合并"""
    out = []
    for k, v in sec.items():
        if norm_head(k) == name:
            out.extend(v)
    return out


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


# 赛道描述的来源分级（用户硬要求：「每个说明都尽量以官方为主」）。
# 这个分级会显示给学生，所以不许含糊——没查证过的不能标 official。
#   official = 有官方出处且已核对原文（章程 / 官方通知）
#   kb       = 知识库整理（来自官方材料但经过转述，未逐字核对）
#   derived  = 我们推断的建议，不是官方要求
TRACK_SRC = {
    # 已逐条核对官方原文（章程 / 官方通知 / 教育部文件 / 大赛官网）
    "挑战杯": "official",     # 挑战杯官方章程第十九条 + 多所高校校赛通知互证
    "iCAN": "official",       # 第二十届 iCAN 官方通知：创新双盲评审 / 创业完成注册 / 挑战企业命题
    "小挑": "official",       # 小挑官方分组：已创业（甲类）/ 未创业（乙类）
    "国创": "official",       # 教高司函〔2020〕4号：创新训练/创业训练/创业实践三类
    "信息安全": "official",   # 全国大学生信息安全竞赛：作品赛 / 创新实践能力赛(CTF)
    "广告艺术": "official",   # 大广赛第17届官方七大类
    "服务外包": "official",   # 第17届服创大赛：企业命题/创业实践/OPC创客/人工智能专项
    "互联网+": "official",    # 中国国际大学生创新大赛官方四赛道
    "计算机设计": "official", # 第19届中国大学生计算机设计大赛官方十一大类
}
TRACK_SRC_NOTE = {
    "official": "官方原文",
    "kb": "知识库整理",
    "derived": "建议（非官方）",
}

RE_TRACK = re.compile(r"^[(（]?\s*\d+\s*[)）、.]\s*(.+?)\s*[：:]\s*(.+)$")


def parse_tracks(key, sec):
    """
    赛道：官方描述以知识库 `## 赛道设置` 为准（Codex 改了 txt 就自动跟上），
    TRACKS 里的 ban / focus / avoid / sections 作为结构化补充。
    知识库没写赛道的赛事 → 返回空数组，前端不显示赛道选择（宁缺毋滥）。
    """
    # 注意：不能用 clean_items——它会先剥掉编号，RE_TRACK 就匹配不上了
    raw = [ln.strip() for ln in sec_get(sec, "赛道设置") if ln.strip()]
    if not raw:
        return []
    tpl = {t["key"]: t for t in TRACKS.get(key, [])}

    out = []
    for ln in raw:
        m = RE_TRACK.match(ln)
        if not m:
            continue
        name, desc = m.group(1).strip(), m.group(2).strip()
        tk = name.replace("赛道", "").strip()
        ext = tpl.get(tk, {})
        out.append({
            "key": tk,
            "name": name,
            # 官方原文（知识库），不改写
            "desc": desc,
            "ban": ext.get("ban", []),
            "ban_note": ext.get("ban_note", ""),
            "focus": ext.get("focus", []),
            "avoid": ext.get("avoid", []),
            "sections": ext.get("sections", []),
            # 告诉前端：后面这些是我们推导的，不是官方原文，显示时要标注
            "derived": bool(ext),
            # 描述本身的可信度：只有逐字核对过官方原文的才标 official
            "src": TRACK_SRC.get(key, "kb"),
        })
    return out


def title_of(s):
    """
    从一条内容里取出「章节标题」本体。
    知识库常见写法：`(2)市场与需求分析（行业 / 人群规模、目标人群构成、核心痛点场景…）`
    括号里是写作要点，不是标题的一部分。
    之前直接按整条长度过滤，把这类真章节（括号很长）误杀了——现在只取括号前的部分。
    """
    s = (s or "").strip()
    s = re.sub(r"^[(（]?\s*\d+\s*[)）、.]\s*", "", s)   # 去编号
    s = re.split(r"[（(]", s, 1)[0]                     # 去括号内的要点
    return s.strip(" ：:，,。")


def is_real_section(s):
    """
    判断一条内容是不是真的「章节标题」（调用前先过 title_of 取标题本体）。
    知识库里有些块标题写着「申报书章节」，内容却是一整句说明
    （例：iCAN 旧版写的是「创新赛道：双盲评审，侧重原创原型，不强制商业化…」）。
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


def build_index():
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

        # 用 sec_get 而非 sec.get：标题可能带括号后缀（如「评分标准（AI 应用挑战赛）」），
        # 精确匹配会整块失配，解析成 0 项
        scoring, orphan = parse_scoring(sec_get(sec, "评分标准"))
        sections = clean_items(sec_get(sec, "申报书章节"))
        # 认不出来的行多半是写错标题的章节（RoboMaster），放到章节前面
        if orphan:
            sections = orphan + sections
        # 先取标题本体（去编号 + 去括号要点），再判断是不是真章节：
        # 知识库里 iCAN / 国创 的「申报书章节」块曾写过赛道说明、结题要求，
        # 直接显示会让学生把一整句当章节名
        sections = [t for t in (title_of(s) for s in sections) if is_real_section(t)]

        pref = clean_items(sec_get(sec, "偏好方向"))
        deduct = " ".join(x.strip() for x in sec_get(sec, "常见扣分点") if x.strip()).strip()

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
            # 赛道：只有知识库真写了 `## 赛道设置` 的才有（目前仅 iCAN），其余为空数组
            "tracks": parse_tracks(key, sec),
        })

    return {
        "version": "2026-09-26.3",
        "source": "由 data/*.txt 解析生成（后端知识库，动态）",
        "count": len(items),
        "items": items,
    }


def main():
    data = build_index()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("生成 %s（%d 个赛事）\n" % (OUT, data["count"]))
    for it in data["items"]:
        print("%-12s 评分%d项 章节%d项 扣分点:%s 文档:%s 赛道:%s" % (
            it["key"], len(it["scoring"]), len(it["sections"]),
            "有" if it["deduct"] else "无", it["doc_type"] or "(待定)",
            "%d个" % len(it["tracks"]) if it["tracks"] else "-"))


if __name__ == "__main__":
    main()
