# -*- coding: utf-8 -*-
"""
fix_rich_wiring.py —— 修复 /api/generate 里富媒体（表格/图表/PPT）的取值接线

问题（2026-09-25 实测，读取 app.py 原文确认）：
  B1. `_run_generation` 里 `history_item` 用了 `rich_charts`，但变量直到后面才赋值
      → UnboundLocalError，深度版生成直接 500
  B2. 解析块读的是 `result["rich_media"]`，而 rich_pipeline 实际写的是
      `result["rich_charts"]/["rich_tables"]/["rich_deck"]`
      → rich_tables 永远是 []、rich_deck 永远是 None，前端拿不到表格和 PPT
  B3. payload 里 `"rich_charts": result.get("rich_charts", [])` 取到的是**原始 dict**，
      而 export_zip / 前端期待的是渲染后的 [{url,title,caption}]
      → 图表 url 缺失，PPT 里插不进图
  B4. `_run_generation` 把 `return {...}` 改写成 `payload = {...}` 后**忘了 return**
      → 整个生成接口返回 data=null（简洁版深度版全挂）

修法：只动取值与 return，不碰 rich_pipeline / chart_renderer / pptx_builder 的业务逻辑。
幂等，可重复跑；每处替换都打印命中次数，别信 ✅ 看数字。

作者：WorkBuddy（阿渡） 2026-09-25
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(BASE, "app.py")

# ---------------------------------------------------------------- B1+B2+B3
OLD_A = '''        mode = data.get("mode", "fast")
        if mode == "deep":
            result = deep_app.invoke(state)
            # 深度版追加：自动生成表格 / 图表 / 路演PPT（失败不阻断主流程）
            try:
                from rich_pipeline import build_rich_assets
                rich = build_rich_assets(result, data.get("competition_name", ""), idea)
                result["rich_charts"] = rich.get("charts", [])
                result["rich_tables"] = rich.get("tables", [])
                result["rich_deck"] = rich.get("deck")
            except Exception as e:
                print(f"[rich] 富媒体生成失败（不影响正文）：{e}")
        else:
            result = fast_app.invoke(state)
'''

NEW_A = '''        mode = data.get("mode", "fast")
        if mode == "deep":
            result = deep_app.invoke(state)
            # 深度版追加：自动生成表格 / 图表 / 路演PPT（失败不阻断主流程）
            try:
                from rich_pipeline import build_rich_assets
                rich = build_rich_assets(result, data.get("competition_name", ""), idea)
                result["rich_charts"] = rich.get("charts") or {}
                result["rich_tables"] = rich.get("tables") or []
                result["rich_deck"] = rich.get("deck")
            except Exception as e:
                print(f"[rich] 富媒体生成失败（不影响正文）：{e}")
        else:
            result = fast_app.invoke(state)

        # ===== 富媒体解析（表格/图表/PPT）：三种来源统一归一，失败不阻断 =====
        # 来源1：rich_pipeline 直接写在 result 上的三个字段（当前主链路）
        # 来源2：result["rich_media"] 的 JSON 字符串（兼容旧写法）
        # 来源3：已经渲染好的 [{url,title,caption}] 列表（直接透传）
        rich_tables = []
        rich_deck = None
        rich_charts = []
        try:
            _charts_raw = result.get("rich_charts")
            rich_tables = result.get("rich_tables") or []
            rich_deck = result.get("rich_deck")

            if not (rich_tables or rich_deck):
                import json as _json
                _rm = (result.get("rich_media") or "").strip()
                if _rm.startswith("```"):
                    _rm = _rm.strip("`")
                    if _rm.lower().startswith("json"):
                        _rm = _rm[4:]
                if _rm:
                    _d = _json.loads(_rm)
                    rich_tables = _d.get("tables") or []
                    rich_deck = _d.get("deck")
                    _charts_raw = _d.get("charts") or _charts_raw

            if isinstance(_charts_raw, dict) and _charts_raw:
                from chart_renderer import render_charts
                rich_charts = render_charts(_charts_raw)
            elif isinstance(_charts_raw, list):
                rich_charts = _charts_raw
        except Exception as _re:
            print(f"[rich] 富媒体解析失败（不影响正文）：{_re}")
        # ===== 富媒体解析结束 =====
'''

# ---------------------------------------------------------------- 删掉旧解析块
OLD_B = '''    import json
    rich_tables = []
    rich_deck = None
    rich_charts = []
    try:
        _rm = (result.get("rich_media") or "").strip()
        if _rm.startswith("```"):
            _rm = _rm.strip("`")
            if _rm.lower().startswith("json"):
                _rm = _rm[4:]
        _d = json.loads(_rm)
        rich_tables = _d.get("tables", [])
        rich_deck = _d.get("deck")
        from chart_renderer import render_charts
        rich_charts = render_charts(_d.get("charts") or {})
    except Exception:
        rich_tables = []
        rich_deck = None
        rich_charts = []

'''

# ---------------------------------------------------------------- B3
OLD_C = '        "rich_charts": result.get("rich_charts", []),'
NEW_C = '        "rich_charts": rich_charts,'

# ---------------------------------------------------------------- B4
OLD_D = '''        "rich_deck": rich_deck
    }
'''
NEW_D = '''        "rich_deck": rich_deck
    }

    return payload
'''

STEPS = [
    ("A 解析块前移+归一（修 B1/B2）", OLD_A, NEW_A),
    ("B 删除失效的 rich_media 解析块", OLD_B, ""),
    ("C payload.rich_charts 改用渲染结果", OLD_C, NEW_C),
    ("D _run_generation 补 return payload", OLD_D, NEW_D),
]

MARKS = ["# ===== 富媒体解析（表格/图表/PPT）", "    return payload\n"]


def main():
    if not os.path.isfile(TARGET):
        print("❌ 找不到 app.py")
        return 1

    with io.open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()
    before = len(src)
    print(f"app.py 原始长度：{before}")

    if all(m in src for m in MARKS):
        print("✅ 四处修复均已存在，跳过（避免和 Codex 的改动重复叠加）")
        return 0

    bak = TARGET + ".bak.wiring"
    try:
        with io.open(bak, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"已备份：{os.path.basename(bak)}")
    except Exception as e:
        print("⚠️ 备份失败：", e)

    ok = True
    for name, old, new in STEPS:
        cnt = src.count(old)
        if cnt == 0:
            print(f"⚠️  {name}：命中 0 处 —— 该处已被改动或写法变了，跳过（请人工核对）")
            ok = False
            continue
        src = src.replace(old, new, 1)
        print(f"✅ {name}：命中 {cnt} 处，替换 1 处")

    with io.open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)

    with io.open(TARGET, "r", encoding="utf-8") as f:
        new_src = f.read()
    print("---- 核验 ----")
    print(f"长度：{before} → {len(new_src)}")
    for m in MARKS:
        print(f"  '{m.strip()[:26]}' 出现 {new_src.count(m)} 次（应为 1）")
    print(f"  'rich_media' 残留 {new_src.count('rich_media')} 处（兼容分支保留 1-2 处属正常）")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
