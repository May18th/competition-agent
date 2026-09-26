"""
富媒体流水线：深度版生成完成后，自动产出
1. 结构化表格（tables）—— 前端 HTML 表格 + Word/PPT 复用
2. 数据图表（charts，PNG）—— 前端展示 + Word/PPT 复用
3. 路演 PPT 结构（deck）—— 前端预览 + 一键导出 .pptx

全部由 LLM 输出结构化 JSON，本地渲染，不依赖外部图像服务。
任何一步失败都会降级，不阻断主流程。
"""
import os
import re
import json

from langchain_core.messages import HumanMessage
from langchain_deepseek import ChatDeepSeek

try:
    from chart_renderer_pro import render as render_chart
except Exception:
    from chart_renderer import render as render_chart

GEN_DIR = os.path.join(os.path.dirname(__file__), "generated")

# 专用 LLM：比主链路更长超时/更多输出 token（结构化 JSON 比较长）
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        import dotenv
        dotenv.load_dotenv()
        # 清洗 NO_PROXY（与 competition_agents 相同：httpx 无法解析 "::1" 和分号分隔）
        _np = os.environ.get("NO_PROXY", "")
        if _np:
            os.environ["NO_PROXY"] = ",".join(
                x for x in _np.replace("::1", "").replace(";", ",").split(",") if x)
            os.environ["no_proxy"] = os.environ["NO_PROXY"]
        _llm = ChatDeepSeek(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.2,
            max_tokens=8000,
            request_timeout=180,
            max_retries=2,
        )
    return _llm


def _extract_json(text):
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    if start < 0:
        raise ValueError("输出中没有 JSON")
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON 不完整")


def _invoke_json(prompt):
    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    return _extract_json(resp.content)


CHART_FORMAT = """
各 type 的 data 格式（严格遵守）：
- bar/column: {"categories":["A","B"],"values":[123,456],"ylabel":"单位"}
- hbar/rank: {"categories":["竞品A","竞品B","我们"],"values":[80,70,95],"xlabel":"评分/性能"}
- line/trend: {"x":["2024","2025"],"series":[{"name":"我们的","values":[1,2]}],"ylabel":"单位"}
- pie/donut: {"labels":["A","B"],"values":[30,70]}
- radar: {"labels":["技术","成本","体验","合规","扩展"],"series":[{"name":"我们","values":[9,7,8,6,8]}]}
- matrix/quadrant: {"points":[{"name":"我们","x":8,"y":7}],"xlabel":"横轴名","ylabel":"纵轴名"}
- architecture/arch: {"layers":[{"name":"应用层","boxes":["用户端","管理后台"]},{"name":"模型层","boxes":["DeepSeek"]}]}
- timeline/gantt: {"stages":[{"name":"需求调研","start":0,"end":2,"label":"第1-2月"}],"xlabel":"时间（月）"}
- funnel: {"labels":["曝光","注册","付费"],"values":[1000,300,80]}
- heatmap/risk: {"rows":["技术风险","市场风险","资金风险"],"cols":["低","中","高"],"values":[[0,1,2],[1,0,1],[0,0,2]]}
- stacked: {"categories":["2024","2025"],"series":[{"name":"软件","values":[30,40]},{"name":"硬件","values":[50,45]}],"ylabel":"万元"}
- gauge/ring: {"value":78,"max":100,"label":"原型完成度","unit":"%"}
每张 chart 顶层字段：id / type / title / caption / source / data。
source 写「来源 + 统计年份」（如「教育部 2024」「中国信通院 2025」），
材料里没有来源的测算值写「行业测算」，并在 caption 里点明是测算口径。
"""


def _load_kb_industry_data(competition):
    """从 data/*.txt 里找当前赛事的「行业数据」章节，喂给图表 LLM 引用真实数字。"""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if not os.path.isdir(data_dir):
        return ""
    comp = str(competition or "")
    for fn in sorted(os.listdir(data_dir)):
        if not fn.endswith(".txt"):
            continue
        name = fn[:-4]
        if name in comp or comp in name or any(k in comp for k in
                ["国创", "挑战杯", "互联网+", "iCAN", "数学建模", "电子设计",
                 "蓝桥杯", "计算机设计", "广告艺术", "服务外包", "信息安全"]):
            try:
                with open(os.path.join(data_dir, fn), encoding="utf-8") as f:
                    txt = f.read()
            except Exception:
                continue
            m = re.search(r"##\s*行业数据[\s\S]*?(?=\n##\s|\Z)", txt)
            if m:
                return m.group(0).strip()
    return ""


def _gen_assets(result, competition, idea, kb_data=""):
    """第一步：让 LLM 设计图表 + 表格"""
    material = f"""
项目：{idea}
赛事：{competition}
一句话定位：{result.get('one_liner','')}
竞品分析：{result.get('competitor_analysis','')[:2500]}
商业模式：{result.get('business_model','')[:2000]}
风险评估：{result.get('risk_analysis','')[:1500]}
技术方案：{result.get('tech_solution','')[:2000]}
实施计划：{result.get('implementation_plan','')[:1500]}
"""
    kb_block = f"\n【可引用的行业真实数据】\n{kb_data}\n" if kb_data else ""
    prompt = f"""你是国家级科创赛事的路演数据可视化专家。根据以下项目材料，设计 6-8 张最有说服力的图表（charts）和 2-4 张关键表格（tables），要达到「2026 国赛超精美图表 A」水准。

{material}
{kb_block}

【图表 A 风格要求 —— 必须遵守】
1. 数据墨水比优先：不要 3D、不要厚重边框；网格线只留极淡虚线；关键数据点要突出。
2. 深色科技蓝底（#0F1535），高亮主色 #818CF8，系列色 #22B8CF / #C084FC / #F59E0B / #34D399 / #FB7185 / #A3E635。
3. 每张图都要「结论式标题 + 一句话洞察 + 数据来源」：标题直接给结论（如「目标市场规模三年翻三倍」），caption 是 20 字内的洞察，source 写来源+年份。
4. 数字必须来自材料或「可引用的行业真实数据」，优先引用上面给的真实数据并标注 source；测算值标「行业测算」并写清口径。每个数据点的 source 只能是三种合法值：①团队输入 ②公开数据（机构+年份，且必须是上面「可引用的行业真实数据」里真实出现的）③测算假设（写明「测算：基于 XX 假设」）。编不出这三种来源的数字一律不准上图；图上没有真实来源的数字，评委一问就露馅。
5. 图表类型必须多样（至少 8 张），且硬性覆盖下面各类，缺一不可：
   - radar 竞品/能力多维对比（1 张）
   - matrix 竞争力定位象限（1 张）
   - funnel 转化漏斗 或 architecture 系统架构（至少 1 张）
   - timeline 实施甘特（1 张）
   - hbar 竞品/能力排名（1 张）
   - heatmap 风险热力矩阵（1 张，rows=风险类型，cols=低/中/高）
   - stacked 构成/占比（1 张，如收入结构、成本结构）
   - gauge 单个关键指标（1 张，如完成度、评分）
   - 其余用 donut / bar / line 补充
   严禁只出 bar / pie / line 三种；预算用 donut、市场规模用 bar、增长用 line、竞品用 radar、竞争力定位用 matrix、转化用 funnel、实施用 timeline、技术用 architecture、排名用 hbar、风险用 heatmap，不要重复。

6. 按「内容 → 图表类型」自动匹配，不要张冠李戴：
   - 预算/成本构成 → donut 或 stacked
   - 市场规模/营收预测 → bar 或 line
   - 增长趋势/累计 → line
   - 竞品多维对比 → radar
   - 竞争定位/性价比 → matrix
   - 转化流程 → funnel
   - 实施计划/里程碑 → timeline
   - 系统/技术架构 → architecture
   - 排名/能力对比 → hbar
   - 风险概率×影响 → heatmap
   - 单个完成度/评分 → gauge

只能输出一个 JSON 对象，不要任何解释文字。格式：
{{
 "charts":[{{"id":"c1","type":"bar","title":"结论式标题","caption":"一句话洞察（20字内）","source":"来源+年份","data":{{...}}}}],
 "tables":[{{"id":"t1","title":"表格标题","header":["维度","我们","竞品A"],"rows":[["价格","99元","199元"]]}}]
}}
{CHART_FORMAT}
要求：
1. id 从 c1/t1 开始编号；type 从上面列表里选
2. 数字必须来自材料或行业真实数据，不能拍脑袋
3. 每张表格 3-6 行、表头不超过 5 列；cells 内容不超过 14 字
4. 图表要能在路演里"一眼看懂"，标题直接给结论（如"目标市场规模三年翻三倍"）
5. 匿名要求：严禁出现任何院校名称、指导老师姓名、团队成员真实姓名，团队一律用「本项目团队」指代"""
    return _invoke_json(prompt)


def _gen_deck(result, competition, idea, assets):
    """第二步：让 LLM 设计 PPT 页面结构（引用 c1/t1 资产）"""
    chart_ids = [c.get("id") for c in assets.get("charts", [])]
    table_ids = [t.get("id") for t in assets.get("tables", [])]
    material = f"""
项目：{idea}
赛事：{competition}
一句话定位：{result.get('one_liner','')}
项目简介：{result.get('project_summary','')[:1500]}
核心创新/技术：{result.get('tech_solution','')[:1800]}
商业模式：{result.get('business_model','')[:1500]}
竞品：{result.get('competitor_analysis','')[:1200]}
实施计划：{result.get('implementation_plan','')[:1000]}
社会价值：{result.get('social_value','')[:800]}
已有 PPT 大纲（可参考其结构）：{result.get('ppt_outline','')[:2000]}
可用图表 id：{chart_ids}
可用表格 id：{table_ids}
"""
    prompt = f"""你是顶级路演 PPT 设计师。根据材料设计一份 12-14 页的路演 PPT 页面结构。

{material}

只能输出一个 JSON 对象：{{"slides":[...]}}，不要任何解释文字。

可用页面类型：
- {{"type":"cover"}} 封面（1页，放最前）
- {{"type":"section","num":"1","title":"章节名","bullets":["本章要点一句话"]}} 章节隔页（2-3个）
- {{"type":"bullets","kicker":"01 / 痛点","title":"页标题","bullets":["**关键词**：一句话说明"]}} 要点页
- {{"type":"metrics","title":"页标题","metrics":["4.5亿：年住院人次","60%：复购意向","3倍：效率提升"]}} 数据卡页
- {{"type":"chart","kicker":"..","title":"页标题","bullets":["要点≤3条"],"chart":"c1"}} 图表页（chart 填上面给的 id）
- {{"type":"table","kicker":"..","title":"页标题","table":"t1","note":"数据口径一句话"}} 表格页（table 填 id）
- {{"type":"closing","title":"谢谢聆听","bullets":["slogan"]}} 结尾页

硬性要求：
1. 叙事线：痛点→方案→技术/创新→市场→商业模式→竞争壁垒→发展规划→社会价值→愿景
2. 信息密度要够：每个 bullets 页 4-6 条要点，每条 25-40 字，必须落到具体细节——
   写清"是谁、做什么、达到什么数字/比例/倍数"，禁止"大幅提升""前景广阔""赋能行业"这类空话
3. 每条尽量写成 "**关键词**：具体说明" 的形式，关键词不超过 6 个字
4. 至少 2 页用 chart（引用给定 id）、至少 1 页用 table（引用给定 id）、至少 1 页 metrics
5. kicker 用"序号 / 章节名"格式，全篇编号连贯
6. 每页可选加 "note"：演讲者备注，一句话讲这页想传达什么（导出后可在 PPT 备注栏看到）
7. 匿名要求：严禁出现任何院校名称、指导老师姓名、团队成员真实姓名，团队一律用「本项目团队」指代"""
    return _invoke_json(prompt)


def _fallback_deck(result, idea):
    """deck 生成失败时的兜底：从 PPT 大纲 markdown 简单拆页"""
    slides = [{"type": "cover"}]
    outline = result.get("ppt_outline", "")
    cur = None
    for line in outline.split("\n"):
        line = line.strip()
        m = re.match(r"^#{1,3}\s+(.*)", line) or re.match(r"^(?:页?\d+[.、:：]|第?\d+页)\s*(.*)", line)
        if m and len(m.group(1)) <= 30:
            if cur:
                slides.append(cur)
            cur = {"type": "bullets", "title": m.group(1).lstrip("#* "), "bullets": []}
        elif cur and line and len(slides) < 14:
            clean = re.sub(r"^[-*•·]\s*", "", line)
            if len(clean) <= 40:
                cur.setdefault("bullets", []).append(clean)
    if cur:
        slides.append(cur)
    slides.append({"type": "closing", "title": "谢谢聆听"})
    return {"slides": slides}


VARIANT_FOR_THEME = {
    "tech": "v1", "cyber": "v1", "finance": "v2", "craft": "v1",
    "medical": "v2", "agri": "v1", "edu": "v1", "social": "v2",
    "ink": "v4", "academic": "v3",
}


def pick_theme(text):
    """按项目内容推断PPT主题：用户没手动指定主题时的兜底。

    打分规则：命中词越多分越高；同分时按 rules 顺序（越具体的赛道排越前）。
    """
    t = str(text or "")
    rules = [
        ("medical", "医疗 健康 护理 康复 护士 医药 问诊 病人 残障 养老 陪护 心理"),
        ("edu", "教育 教学 学生 校园 课程 学习 培训 教师 儿童 少儿 高考 考研"),
        ("agri", "农业 种植 养殖 农机 乡村 农户 生态 林业 畜牧 粮食 乡村振兴"),
        ("craft", "智能制造 机械 材料 建筑 工业 装备 机器人 嵌入式 传感器 硬件 自动化"),
        ("social", "公益 助老 无障碍 社区 志愿 慈善 弱势 留守儿童 帮扶"),
        ("ink", "文化 非遗 文创 古籍 书法 国风 传统 博物馆 艺术 文学 汉服"),
        ("cyber", "人工智能 大模型 算法 神经网络 机器学习 深度学习 自动驾驶 算力"),
        ("academic", "论文 开题 结题 科研 课题 学术 学位 毕业设计"),
        ("finance", "金融 支付 供应链 财务 融资 保险 银行 结算 投融"),
        ("tech", "平台 系统 软件 数据 互联网 区块链 物联网 小程序 APP 数字化"),
    ]
    best, best_score = "tech", 0
    for key, words in rules:
        score = sum(1 for w in words.split() if w in t)
        if score > best_score:
            best, best_score = key, score
    return best


def build_rich_assets(result, competition="", idea="", theme=None):
    """主入口：返回 {"charts":[...], "tables":[...], "deck":{...}, "theme":...}；失败字段为空"""
    out = {"charts": [], "tables": [], "deck": None}
    os.makedirs(GEN_DIR, exist_ok=True)

    # 主题：用户指定优先，没指定就按项目内容推断
    if not theme:
        theme = pick_theme(" ".join([idea or "", competition or "",
                                     result.get("one_liner", "") or ""]))
    out["theme"] = str(theme).lower()
    print(f"[rich] PPT 主题：{out['theme']}")

    # ---- 1. 图表 + 表格 ----
    assets = {}
    try:
        kb_data = _load_kb_industry_data(competition)
        assets = _gen_assets(result, competition, idea, kb_data) or {}
    except Exception as e:
        print(f"[rich] 图表/表格设计失败，降级：{e}")

    charts, tables = [], []
    for c in (assets.get("charts") or [])[:8]:
        cid = str(c.get("id") or f"c{len(charts)+1}")
        path = render_chart(dict(c, id=cid), GEN_DIR, theme=theme)
        if path:
            safe = os.path.basename(path)
            charts.append({
                "id": cid, "title": c.get("title", ""),
                "caption": c.get("caption", ""),
                "source": c.get("source", ""),
                "url": f"/generated/{safe}",
                # 保留原始数值：PNG 不可 hover，前端要用 ECharts 重绘才支持「显示具体数值」
                "spec": c,
            })
            print(f"[rich] 图表 {cid} 渲染完成 -> {safe}")
    for t in (assets.get("tables") or [])[:5]:
        if not t.get("header") or not t.get("rows"):
            continue
        tables.append({
            "id": str(t.get("id") or f"t{len(tables)+1}"),
            "title": t.get("title", ""),
            "header": t["header"][:6],
            "rows": [r[:6] for r in t["rows"][:7]],
        })

    # ---- 2. PPT 结构 ----
    try:
        deck = _gen_deck(result, competition, idea, assets)
        slides = deck.get("slides") or []
    except Exception as e:
        print(f"[rich] PPT 结构生成失败，使用大纲兜底：{e}")
        slides = None
    if not slides:
        try:
            deck = _fallback_deck(result, idea)
            slides = deck.get("slides") or []
        except Exception as e:
            print(f"[rich] PPT 兜底也失败：{e}")
            deck = None
    if slides:
        table_map = {t["id"]: t for t in tables}
        chart_ids = {c["id"] for c in charts}
        norm = []
        for s in slides[:18]:
            if not isinstance(s, dict):
                continue
            s.setdefault("type", "bullets")
            # table 引用 -> 实体
            if isinstance(s.get("table"), str):
                s["table"] = table_map.get(s["table"])
            # chart 引用必须存在，否则退化为普通要点页
            if s.get("chart") and s["chart"] not in chart_ids:
                s.pop("chart", None)
                s["type"] = "bullets"
            if s["type"] == "chart" and not s.get("chart"):
                s["type"] = "bullets"
            norm.append(s)
        if norm and norm[0].get("type") != "cover":
            norm.insert(0, {"type": "cover"})
        deck["slides"] = norm
        deck.setdefault("project", idea[:30])
        deck.setdefault("one_liner", result.get("one_liner", ""))
        deck.setdefault("competition", competition)
        deck.setdefault("theme", out["theme"])
        # 不同赛道配不同版式：学术类要序号列表居中，水墨类要留白，医疗类偏极简
        deck.setdefault("variant", VARIANT_FOR_THEME.get(out["theme"], "v1"))
        out["deck"] = deck

    out["charts"] = charts
    out["tables"] = tables
    return out
