# -*- coding: utf-8 -*-
"""范文检索层：从用户描述抽关键词 + 按标签交集打分检索范文。"""
from kb_samples import list_samples, MODULE_TAGS, TRACK_TAGS, FEATURE_TAGS


# 别名映射：标签 -> 常见表述（含标签本身）。全部小写后做字符串包含匹配。
_ALIAS_MAP = {
    "web网站": ["web网站", "web", "网站", "网页"],
    "人工智能": ["人工智能", "ai", "aigc", "机器学习", "深度学习", "大模型", "模型", "智能体"],
    "文化文旅": ["文化文旅", "文旅", "苏轼", "诗词", "传统文化", "文化"],
    "非遗": ["非遗", "非物质文化遗产"],
    "校园服务": ["校园服务", "校园"],
    "乡村振兴": ["乡村振兴", "乡村", "助农", "农业"],
    "4人团队": ["4人团队", "四人团队", "四名成员", "4人", "四人"],
    "学生团队": ["学生团队", "学生"],
    "有软著": ["有软著", "软著", "软件著作权"],
    "已试点": ["已试点", "试点", "落地"],
    "初创阶段": ["初创阶段", "初创", "早期"],
    "用户量小": ["用户量小", "用户量"],
    "项目简介": ["项目简介"],
    "社会价值": ["社会价值"],
    "实践过程": ["实践过程", "实践"],
    "商业模式": ["商业模式"],
    "创新点": ["创新点", "创新"],
    "风险分析": ["风险分析", "风险"],
}


def extract_keywords(text):
    """从用户描述里抽关键词，返回命中的标签列表。

    优先尝试 jieba 分词；不可用则退化为词表别名字符串包含匹配。
    """
    text = (text or "").lower()
    if not text:
        return []

    # 尝试 jieba 分词，失败则用原始文本做包含匹配
    tokens = None
    try:
        import jieba  # type: ignore
        tokens = [w.lower() for w in jieba.lcut(text)]
    except Exception:
        tokens = None

    matched = []
    for tag, aliases in _ALIAS_MAP.items():
        hit = False
        if tokens:
            hit = any(a in tokens for a in aliases)
        if not hit:
            hit = any(a in text for a in aliases)
        if hit:
            matched.append(tag)
    return matched


def _tag_weight(tag):
    if tag in MODULE_TAGS:
        return 3
    if tag in TRACK_TAGS:
        return 2
    if tag in FEATURE_TAGS:
        return 1
    return 1


def search_samples(user_keywords, module_tag=None, top_k=3, max_chars=3000):
    """按标签交集打分检索范文，返回格式化文本；无命中返回空串。"""
    try:
        samples = list_samples()
    except Exception:
        return ""

    kws = set(user_keywords or [])
    scored = []
    for s in samples:
        tags = set(s.get("tags") or [])
        # 指定模块时，只取带该模块标签的范文（模块是硬匹配）
        if module_tag and module_tag not in tags:
            continue
        if kws:
            inter = kws & tags
            if not inter:
                continue   # 给了关键词但无任何交集 → 这篇不相关，跳过
            score = sum(_tag_weight(k) for k in inter)
        else:
            score = 0      # 未给关键词：退化为按模块 + 范文自带评分兜底
        # 范文自带评分只做微调（最高 +0.92），不能压过标签匹配，更不能单独促成命中
        score += (s.get("score") or 0) * 0.01
        scored.append((score, s))

    scored.sort(key=lambda x: (-x[0], -x[1].get("score", 0)))
    top = [s for _, s in scored[:top_k]]
    if not top:
        return ""

    # 拼接，整段丢弃超出的（不截断半句）
    parts, total = [], 0
    for s in top:
        content = (s.get("content") or "").strip()
        if not content:
            continue
        if total + len(content) > max_chars:
            break
        parts.append(content)
        total += len(content)
    return "\n\n".join(parts)
