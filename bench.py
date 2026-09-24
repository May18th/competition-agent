"""后端基准测试：固定样例跑生成，记录 创意分/文档分/字数/耗时。

用法：
    python bench.py                 # 真实调用 DeepSeek（消耗额度）
    python bench.py --mock          # 用假 LLM 快速验证结构（不耗额度）
    python bench.py --csv out.csv   # 结果追加写入 CSV（便于跨版本对比）
"""
import sys
import time
import csv
import os
import io
from contextlib import redirect_stdout


SAMPLES = [
    ("iCAN大学生创新创业大赛", "一款面向高校实验室的智能危化品全流程管理系统"),
    ("挑战杯", "一款基于区块链的农产品溯源与助农平台"),
    ("互联网+大赛", "一款面向校园的智能垃圾分类回收系统"),
]


def make_state(competition_name, idea):
    return {
        "competition_name": competition_name,
        "rule_content": "",
        "idea": idea,
        "proposal_draft": "",
        "parsed_rules": "",
        "similarity_report": "",
        "competitor_analysis": "",
        "business_model": "",
        "risk_analysis": "",
        "tech_solution": "",
        "implementation_plan": "",
        "social_value": "",
        "project_summary": "",
        "proposal": "",
        "judge_feedback": "",
        "proposal_analysis": "",
        "defense_questions": "",
        "ppt_outline": "",
        "speech_script": "",
        "one_liner": "",
        "idea_score": 0,
        "idea_feedback": "",
        "score": 0,
        "approved": False,
        "revision_count": 0,
    }


def main():
    mock = "--mock" in sys.argv
    csv_path = None
    if "--csv" in sys.argv:
        try:
            csv_path = sys.argv[sys.argv.index("--csv") + 1]
        except IndexError:
            print("--csv 需要跟一个文件路径")
            return

    import competition_agents as ca

    if mock:
        class FakeLLM:
            class Resp:
                content = (
                    "创新性：80分\n可行性：75分\n市场价值：70分\n技术壁垒：65分\n社会价值：85分\n"
                    "结构完整性：90分\n逻辑清晰度：85分\n数据支撑：80分\n格式规范：88分\n说服力：86分"
                )
            def invoke(self, *a, **k):
                return self.Resp()
        ca.llm = FakeLLM()

    header = ["mode", "sample", "idea_score", "doc_score", "words", "seconds"]
    rows = []
    print(f"{'模式':<5}{'样例':<5}{'创意分':>7}{'文档分':>7}{'字数':>8}{'耗时':>9}")
    for mode in ("fast", "deep"):
        app = ca.fast_app if mode == "fast" else ca.deep_app
        for idx, (comp, idea) in enumerate(SAMPLES, 1):
            t0 = time.time()
            with redirect_stdout(io.StringIO()):
                r = app.invoke(make_state(comp, idea))
            dt = round(time.time() - t0, 1)
            row = [mode, str(idx), r.get("idea_score", 0), r.get("score", 0),
                   len(r.get("proposal") or ""), dt]
            rows.append(row)
            print(f"{mode:<5}{idx:<5}{row[2]:>7}{row[3]:>7}{row[4]:>8}{row[5]:>9.1f}s")

    if csv_path:
        append = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if not append:
                w.writerow(header)
            w.writerows(rows)
        print(f"已写入 {csv_path}")


if __name__ == "__main__":
    main()
