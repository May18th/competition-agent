# -*- coding: utf-8 -*-
"""验证 pptx_builder 的长段落拆分 + 自动分页（不依赖 LLM / 服务）"""
import os, sys
from pptx import Presentation
from pptx.util import Emu

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pptx_builder as PB

LONG = ("**全链路服务闭环**：从入院评估、护工匹配、在岗打卡、护理记录到出院结算与售后仲裁，"
        "全流程平台化留痕，家属可随时查看每一次服务的时间、地点、内容与照片证据，"
        "出现纠纷时以平台记录作为责任界定依据，显著降低家属与护工之间的信息不对称")

DECK = {
    "project": "护途 CareWay",
    "one_liner": "让每一次住院都有人管、有据可依",
    "competition": "iCAN 大学生创新创业大赛",
    "slides": [
        {"type": "cover", "title": "护途 CareWay"},
        {"type": "bullets", "kicker": "01 / 痛点", "title": "住院陪护市场痛点",
         "bullets": [
             LONG,
             "**找护工难**：靠熟人介绍，质量无从考证，家属往往在病房走廊临时抓人",
             "**价格不透明**：同类服务差价可达 2 倍，且中途加价情况普遍",
             "**纠纷难界定**：出了问题责任说不清，双方各执一词缺乏第三方记录",
             "**陪护质量参差**：无统一培训标准，护理操作规范执行率不足五成",
             "**家属精力透支**：长期请假陪护影响工作，身心负担沉重",
             "**院方管理缺位**：外包护工游离于医院管理体系之外",
             "**信息孤岛**：护工档案、评价、保险数据分散在不同机构",
             "**支付不便利**：现金交易为主，缺乏发票与保障凭证",
             "**旺季供给不足**：春节期间护工返乡，缺口急剧放大",
         ],
         "metrics": ["4.5亿：全国年住院人次", "60%：家属请假陪护比例", "38%：护工无培训上岗"]},
        {"type": "bullets", "kicker": "02 / 方案", "title": "我们的解决方案",
         "bullets": ["**三重背调**：身份、健康证、从业记录逐一核验",
                     "**统一定价**：平台明码标价，杜绝中途加价",
                     "**全程留痕**：打卡 + 护理记录 + 照片证据链",
                     "**保险兜底**：每单附带意外险与责任险"],
         "chart": "demo"},
        {"type": "table", "kicker": "03 / 竞品", "title": "竞品对比",
         "table": {"header": ["维度", "护途", "传统中介", "平台A", "医院外包"],
                   "rows": [["资质审核", "三重背调", "无", "证件拍照", "院内备案"],
                            ["价格", "统一定价", "口头议价", "抽成20%", "固定套餐"],
                            ["保险", "每单双险", "无", "单险", "部分"],
                            ["留痕", "全程证据链", "无", "部分打卡", "纸质记录"],
                            ["纠纷处理", "平台仲裁", "自行协商", "客服介入", "院方协调"],
                            ["覆盖城市", "12", "1", "35", "1"],
                            ["护工数量", "8600", "200", "52000", "1500"],
                            ["培训体系", "自有学院", "无", "第三方", "院内培训"],
                            ["响应速度", "2小时", "1-3天", "4小时", "半天"],
                            ["复购率", "63%", "30%", "45%", "55%"]]}},
        {"type": "section", "num": "3", "title": "商业模式",
         "bullets": ["抽佣 + 会员 + 保险分成"]},
        {"type": "metrics", "kicker": "04 / 财务", "title": "三年财务预测",
         "metrics": ["120万：首年营收", "380万：次年营收", "860万：第三年营收", "62%：综合毛利率"],
         "bullets": ["**首年**：聚焦 3 城标杆医院，跑通单城模型",
                     "**次年**：复制到 12 城，护工池扩至 8000+",
                     "**第三年**：开放城市合伙人，启动保险分润"]},
        {"type": "closing", "title": "谢谢聆听", "bullets": ["欢迎评委指导"]},
    ],
}

OUT = "_ppt_pagination_test.pptx"
PB.build_deck(DECK, OUT, chart_paths={"demo": "_chart_test/demo.png"})

prs = Presentation(OUT)
print("文件: %s  %.1f KB" % (OUT, os.path.getsize(OUT) / 1024.0))
print("总页数: %d" % len(prs.slides))

EMU_IN = 914400.0
H = prs.slide_height / EMU_IN
W = prs.slide_width / EMU_IN
FOOT_TOP = 6.95     # 页脚本身就画在 7.0，不算越界
bad = 0
alltext = []
for i, sl in enumerate(prs.slides, 1):
    titles = []
    ncell = 0
    for sh in sl.shapes:
        try:
            l, t = sh.left / EMU_IN, sh.top / EMU_IN
            w, h = sh.width / EMU_IN, sh.height / EMU_IN
        except Exception:
            continue
        txt = sh.text_frame.text.strip() if sh.has_text_frame else ""
        if txt:
            titles.append(txt.split("\n")[0][:26])
            alltext.append(txt)
        if getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                for c in row.cells:
                    if c.text.strip():
                        ncell += 1
                        alltext.append(c.text.strip())
        if txt and t >= FOOT_TOP:          # 页脚
            continue
        if not txt and (t < -0.01 or h > 6.0):   # 封面装饰圆 / 渐变背景
            continue
        if t + h > FOOT_TOP + 0.02 or t < -0.01 or l + w > W + 0.02:
            bad += 1
            print("  [越界] p%d  t=%.2f b=%.2f r=%.2f  %s"
                  % (i, t, t + h, l + w, txt[:20]))
    print("p%-2d %-14s | 形状%-3d 表格单元%s"
          % (i, titles[0] if titles else "-", len(sl.shapes), ncell or ""))

print("\n越界形状数: %d" % bad)

# 内容完整性：统计所有文本（含表格）里有没有被砍掉的关键数据
full = "\n".join(alltext)
for key in ["8600", "63%", "860万", "护工池", "城市合伙人", "信息孤岛", "支付不便利"]:
    print("  含 %-8s : %s" % (key, key in full))
print("  省略号出现次数: %d" % full.count("…"))
