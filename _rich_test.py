# -*- coding: utf-8 -*-
"""真跑一次完整生成，验证申报书篇幅与排版效果。

用法：python _rich_test.py fast|deep
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import competition_agents as ca
import app as A

IDEA = (
    "面向独居老人的智适应陪护机器人：视觉与毫米波雷达融合做跌倒检测，"
    "输出置信度而非二值报警；用药提醒通过药盒仓位检测与取药确认记录漏服，"
    "并依据老人认知状态调整提醒时机；情感陪伴调用大模型接口做日常对话。"
)
COMP = "iCAN大学生创新创业大赛"


def base_state():
    return {
        "competition_name": COMP, "rule_content": "", "idea": IDEA,
        "proposal_draft": "", "parsed_rules": "", "similarity_report": "",
        "competitor_analysis": "", "business_model": "", "risk_analysis": "",
        "tech_solution": "", "implementation_plan": "", "social_value": "",
        "project_summary": "", "proposal": "", "judge_feedback": "",
        "proposal_analysis": "", "defense_questions": "", "ppt_outline": "",
        "speech_script": "", "one_liner": "", "rich_media": "",
        "idea_score": 0, "idea_feedback": "", "score": 0,
        "approved": False, "iterate": False,
    }


def cjk(t):
    return len(re.sub(r'[#*`\-\|>\[\]（）()\s]', '', t or ''))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'fast'
    graph = ca.fast_app if mode == 'fast' else ca.deep_app
    t0 = time.time()
    res = graph.invoke(base_state())
    p = res['proposal']
    heads = re.findall(r'^#{1,3} .*$', p, re.M)
    empty = []
    lines = p.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r'^#{1,3} ', ln):
            j = i + 1
            body = ''
            while j < len(lines) and not re.match(r'^#{1,3} ', lines[j]):
                body += lines[j]
                j += 1
            if cjk(body) < 60:
                empty.append(ln.strip()[:40])
    print('[%s] 耗时 %.0fs' % (mode, time.time() - t0))
    print('[%s] 正文字数 %d，标题数 %d' % (mode, cjk(p), len(heads)))
    print('[%s] 疑似空小节：%s' % (mode, empty or '无'))
    doc = A._build_docx(
        '智适应助老陪护机器人项目申报书', p, doc_type='default',
        subtitle=COMP, school='某某大学', team='启明创新团队', advisor='张三 教授')
    out = '_verify_out/丰富版_%s_申报书.docx' % mode
    doc.save(out)
    print('[%s] 已导出 %s（%d 字节）' % (mode, out, os.path.getsize(out)))
    with open('_verify_out/丰富版_%s_正文.md' % mode, 'w', encoding='utf-8') as f:
        f.write(p)


if __name__ == '__main__':
    main()
