# -*- coding: utf-8 -*-
"""生成「图表升级前后对比」HTML 页面。

读取 _verify_out/chart_compare_meta.json + charts_before/ + charts_after/，
输出 _verify_out/图表升级前后对比.html（图片用相对路径引用）。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_verify_out")
DST = os.path.join(OUT, "图表升级前后对比.html")

UPGRADES = [
    ("分辨率", "dpi 110，Word/PPT 放大发糊", "dpi 200，投影/打印都清晰", "高"),
    ("画布", "10×5.4 紧凑", "11×6.2 + 圆角卡片打底，留白舒展", "中"),
    ("标题区", "普通一行标题", "强调色竖条 + 结论式主标题 + 洞察底条", "高"),
    ("配色", "纯色平涂", "同色系渐变填充，层次感", "高"),
    ("柱形", "直角平面", "圆角顶 + 竖向渐变 + 底部投影，「我们的项目」高亮强调色", "高"),
    ("数据标签", "裸数字", "值 + 单位，颜色随底色亮度自适应", "中"),
    ("网格线", "四边框 + 实线网格", "只留横向虚线，透明度 0.35，不抢数据", "中"),
    ("饼/环形图", "百分比挤在扇区里", "环形 + 中心总计 + 引导线外置标签", "高"),
    ("雷达图", "单层细线", "多层半透明填充 + 卡片化图例 + 节点描边", "高"),
    ("甘特图", "直角色条", "圆角条 + 横向渐变 + 投影 + 末阶段高亮", "高"),
    ("架构图", "方块堆叠", "圆角分层卡片 + 层名标签块 + 层间箭头", "高"),
    ("象限图", "散点 + 十字线", "象限浅色分区 + 白描边点 + 引导线命名", "中"),
]


def main():
    with open(os.path.join(OUT, "chart_compare_meta.json"), encoding="utf-8") as f:
        meta = json.load(f)

    rows = ""
    for i, (dim, before, after, lvl) in enumerate(UPGRADES):
        badge = f'<span class="lvl lv-{i%2}">{lvl}</span>'
        rows += f"<tr><td>{dim}</td><td class='b'>{before}</td><td class='a'>{after}</td><td>{badge}</td></tr>\n"

    cards = ""
    for m in meta:
        cards += f"""
    <section class="cmp">
      <div class="cmp-head">
        <span class="tag">{m['type']}</span>
        <h3>{m['title']}</h3>
        <p class="cap">{m['caption']}</p>
      </div>
      <div class="pair">
        <figure>
          <figcaption><i class="dot old"></i>升级前 · {m['before_kb']} KB</figcaption>
          <img src="charts_before/{m['before']}" alt="升级前" loading="lazy">
        </figure>
        <figure class="new">
          <figcaption><i class="dot new"></i>升级后 · {m['after_kb']} KB</figcaption>
          <img src="charts_after/{m['after']}" alt="升级后" loading="lazy">
        </figure>
      </div>
    </section>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>图表升级前后对比 · 国赛超精美版</title>
<style>
  :root {{
    --bg:#F5F7FB; --card:#FFFFFF; --line:#E4E8F1; --txt:#1F2430;
    --dim:#6B7385; --old:#98A2B3; --new:#2563EB; --accent:#0EA5E9;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:"Microsoft YaHei","PingFang SC",sans-serif; background:var(--bg); color:var(--txt); padding:32px 20px 60px; }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  header h1 {{ font-size:26px; font-weight:800; }}
  header h1 em {{ font-style:normal; color:var(--new); }}
  header p {{ color:var(--dim); margin-top:8px; font-size:14px; }}
  .stats {{ display:flex; gap:14px; margin:22px 0 8px; flex-wrap:wrap; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 20px; }}
  .stat b {{ display:block; font-size:24px; color:var(--new); }}
  .stat span {{ font-size:12.5px; color:var(--dim); }}
  h2.sec {{ margin:38px 0 16px; font-size:19px; border-left:4px solid var(--accent); padding-left:10px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border-radius:12px; overflow:hidden; box-shadow:0 1px 3px rgba(15,23,42,.06); font-size:14px; }}
  th,td {{ padding:11px 14px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ background:#F0F4FA; font-size:13px; color:var(--dim); font-weight:600; }}
  td.b {{ color:var(--old); }}
  td.a {{ color:#1D4ED8; font-weight:600; }}
  .lvl {{ display:inline-block; padding:2px 10px; border-radius:20px; font-size:12px; }}
  .lv-0 {{ background:#DBEAFE; color:#1D4ED8; }}
  .lv-1 {{ background:#E0F2FE; color:#0369A1; }}
  .cmp {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; margin-top:22px; box-shadow:0 1px 3px rgba(15,23,42,.06); }}
  .cmp-head {{ margin-bottom:14px; }}
  .tag {{ display:inline-block; background:#EFF6FF; color:#1D4ED8; font-size:12px; padding:3px 10px; border-radius:20px; margin-bottom:8px; }}
  .cmp-head h3 {{ font-size:16.5px; }}
  .cmp-head .cap {{ font-size:13px; color:var(--dim); margin-top:4px; }}
  .pair {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  figure {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#0F1535; }}
  figure.new {{ border-color:#BFDBFE; box-shadow:0 2px 10px rgba(37,99,235,.12); }}
  figcaption {{ padding:8px 12px; background:#F8FAFC; font-size:12.5px; color:var(--dim); display:flex; align-items:center; gap:6px; }}
  figure.new figcaption {{ color:#1D4ED8; font-weight:600; }}
  .dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
  .dot.old {{ background:var(--old); }}
  .dot.new {{ background:var(--new); }}
  img {{ width:100%; display:block; }}
  footer {{ margin-top:36px; color:var(--dim); font-size:12.5px; text-align:center; }}
  @media (max-width:820px) {{ .pair {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>申报书图表 <em>「国赛超精美版」</em> 升级对比</h1>
    <p>同一份深度版真实数据（智能试剂柜 · 历史记录 #41），旧渲染器 chart_renderer vs 新渲染器 chart_renderer_pro。新渲染器已切换为生产默认（可用环境变量 CHART_RENDERER=legacy 回退）。</p>
    <div class="stats">
      <div class="stat"><b>{len(meta)}</b><span>张图表全部升级</span></div>
      <div class="stat"><b>{len(UPGRADES)}</b><span>个升级维度</span></div>
      <div class="stat"><b>110→200</b><span>输出分辨率 dpi</span></div>
      <div class="stat"><b>0 改动</b><span>旧渲染器原样保留，可随时回退</span></div>
    </div>
  </header>

  <h2 class="sec">一、优化点对照表</h2>
  <table>
    <tr><th>维度</th><th>升级前</th><th>升级后</th><th>影响</th></tr>
    {rows}
  </table>

  <h2 class="sec">二、逐图对比（升级前 → 升级后）</h2>
  {cards}

  <footer>生成时间 2026-09-26 · 科创赛事多智能体创作助手 · chart_renderer_pro.py</footer>
</div>
</body>
</html>"""
    with open(DST, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML 已生成：", DST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
