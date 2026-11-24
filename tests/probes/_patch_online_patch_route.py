#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给线上 app.py 加 /api/scorecard/patch 路由（定向补写）。

基线必须已含诊断路由与清理链，脚本会先断言，避免拿旧文件覆盖掉已有功能。
用法（在 app_live2.py 同目录执行）：python _patch_online_patch_route.py
"""
import io
import sys

SRC = "app_live2.py"
OUT = "app_patch_route.py"
ANCHOR = "@app.route('/api/scorecard', methods=['POST'])"

ROUTE = '''@app.route('/api/scorecard/patch', methods=['POST'])
def scorecard_patch_api():
    """按评分缺口定向补写：只改缺分的那一两章，补完自动复检（会调用模型，10~40 秒）。

    不写历史库、不覆盖原稿，只把「补写前后对比 + 补写后正文」返回给调用方。
    """
    data = request.get_json(silent=True) or {}
    try:
        from scorecard_patch import patch_until_clean
        track = (data.get('track') or '').strip() or None
        hid = data.get('history_id')
        if hid:
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT result_data, mode, competition_name FROM history WHERE id=?",
                    (hid,)).fetchone()
            finally:
                conn.close()
            if not row:
                return jsonify({"success": False, "error": "记录不存在"}), 404
            import json as _json
            rec = _json.loads(row[0] or "{}")
            mode = (data.get('mode') or row[1] or 'fast')
            comp = (data.get('competition_name') or row[2] or '')
        else:
            rec = {"proposal": (data.get('proposal') or '')}
            mode = data.get('mode') or 'fast'
            comp = (data.get('competition_name') or '').strip()
        if not (rec.get('proposal') or '').strip():
            return jsonify({"success": False, "error": "缺少正文"}), 400
        result = patch_until_clean(rec, comp, track, mode,
                                   limit=int(data.get('limit') or 2))
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:200]}), 500


'''


def main():
    src = io.open(SRC, encoding="utf-8", newline="").read()

    # 基线断言：已有功能一个都不能少
    checks = {"api/scorecard": 1, "_strip_cliches": 2, "def _run_generation": 1,
              "scorecard_patch_api": 0}
    for needle, want in checks.items():
        got = src.count(needle)
        if got != want:
            sys.exit("基线异常：%s 出现 %d 次，期望 %d（别用旧文件当基线）" % (needle, got, want))

    if src.count(ANCHOR) != 1:
        sys.exit("锚点异常：%d" % src.count(ANCHOR))

    out = src.replace(ANCHOR, ROUTE + ANCHOR, 1)
    io.open(OUT, "w", encoding="utf-8", newline="").write(out)
    print("ok: %d -> %d 字符，新增 %d 行" % (len(src), len(out), out.count("\n") - src.count("\n")))
    print("部署后须断言：api/scorecard 2 处、scorecard_patch_api 1 处")


if __name__ == "__main__":
    main()
