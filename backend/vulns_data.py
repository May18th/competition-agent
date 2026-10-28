# -*- coding: utf-8 -*-
"""漏洞库数据层（M7 拆分：从 app.py 抽出的自包含解析/读写逻辑，零 Flask 依赖）。"""
import os
import re
import json
from datetime import datetime

# 数据源：.data/漏洞库.md 首次解析入库到 assets/data/vulns.json，之后以 JSON 为准（存储同步）。
# 字段：id / level / name / status / owner / round / experience / distilled / category / updated_at
_VULNS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'assets', 'data', 'vulns.json')
_VULNS_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.data', '漏洞库.md')
_LEVEL_TAG = {"一": "high", "二": "medium", "三": "low"}
_LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}


def _strip_status_emoji(s):
    """去掉状态列的前缀表情符号并归一化。"""
    s = (s or '').strip()
    s = re.sub(r'^[✅⚠️❌🟡🟢🔴\s]+', '', s)
    s = s.strip() or '未修复'
    if '已修复' in s:
        return '已修复'
    if '部分' in s or '待收敛' in s or '收敛' in s:
        return '部分修复'
    if '待核实' in s:
        return '待核实'
    if '待确认' in s or '待定' in s:
        return '待确认'
    if '已确认' in s:
        return '已确认'
    if '已核' in s:
        return '已核'
    return '未修复'


def _infer_vuln_category(name):
    """按名称做根因/模块归因（供 /api/vulns/stats 聚合，未命中归「其他」）。"""
    n = name or ''
    if any(k in n for k in ('隔离', 'token', '明文', '安全', '泄露', '隐私')):
        return '安全'
    if any(k in n for k in ('口径', '字数', '文案', '数据', '评分', '档位', 'stats', '自认')):
        return '数据口径'
    if any(k in n for k in ('截断', 'Markdown', '重复', '渲染', '图标', '配色', '图片', 'PPT', '目录', '标题', '占位')):
        return '渲染/输出质量'
    if any(k in n for k in ('拆分', '巨石', '脚本', '死代码', 'TTFB', '体积', '性能', '健康')):
        return '工程架构'
    if any(k in n for k in ('移动端', '发烫', '弹窗', '遮挡', '功耗', '体验')):
        return '体验'
    if any(k in n for k in ('待核实', '规则', '赛道')):
        return '规则待核实'
    if any(k in n for k in ('文件名', 'favicon', 'robots', '细节', '缺失')):
        return '细节'
    return '其他'


def _parse_vulns_md():
    """解析 .data/漏洞库.md 的高/中/低三张表格，返回结构化列表。"""
    items = []
    if not os.path.isfile(_VULNS_MD):
        return items
    try:
        with open(_VULNS_MD, encoding='utf-8') as f:
            lines = f.read().splitlines()
    except Exception:
        return items
    level = None
    _md_mtime = ""
    try:
        _md_mtime = datetime.fromtimestamp(os.path.getmtime(_VULNS_MD)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    for line in lines:
        m = re.match(r'^##\s*([一二三])、', line)
        if m:
            level = _LEVEL_TAG.get(m.group(1))
            continue
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if not cells or cells[0] in ('ID', '') or set(cells[0]) <= set('- '):
            continue
        if len(cells) < 5:
            continue
        # 新格式（193-195 轮新增行，7 列）：ID|漏洞|类别|状态|责任人|轮次|经验
        # 旧格式（5 列）：ID|漏洞|状态|责任人|轮次/证据
        if len(cells) >= 7:
            vid, name = cells[0], cells[1]
            _cat = cells[2]
            status = _strip_status_emoji(cells[3])
            owner = cells[4]
            round_ev = cells[5]
            experience = cells[6]
        else:
            vid, name = cells[0], cells[1]
            _cat = ""
            status = _strip_status_emoji(cells[2])
            owner = cells[3]
            round_ev = cells[4]
            experience = ""
        items.append({
            "id": vid,
            "level": level or "low",
            "name": name,
            "status": status,
            "owner": owner,
            "round": round_ev,
            "evidence": round_ev,
            "experience": experience,
            "distilled": False,
            "category": _cat or _infer_vuln_category(name),
            "updated_at": _md_mtime
        })
    return items


def _save_vulns(items):
    os.makedirs(os.path.dirname(_VULNS_FILE), exist_ok=True)
    with open(_VULNS_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _load_vulns():
    """读漏洞库；无 JSON、解析失败、或 md 比 JSON 新时回退解析 md 并落盘。

    关键：vulns.json 是 gitignored 的运行时缓存。md（source of truth）一旦被
    更新（owner/状态/经验列改动），若不按 mtime 失效，服务会一直返回旧
    JSON，解析层修了也看不到效果——所以这里用 md 更新于 JSON 作为重解析信号。
    """
    json_mtime = 0.0
    md_mtime = 0.0
    try:
        json_mtime = os.path.getmtime(_VULNS_FILE)
    except Exception:
        pass
    try:
        md_mtime = os.path.getmtime(_VULNS_MD)
    except Exception:
        pass
    if os.path.isfile(_VULNS_FILE) and json_mtime > md_mtime:
        try:
            with open(_VULNS_FILE, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    items = _parse_vulns_md()
    _save_vulns(items)
    return items
