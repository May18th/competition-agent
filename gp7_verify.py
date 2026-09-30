# -*- coding: utf-8 -*-
"""309 轮：三份演示样例校验（JSON / 字数 / 字段差集 / 抽查 / 评分自洽）。"""
import json
import os
import re

BASE = '/opt/comp-agent'
STATIC = os.path.join(BASE, 'static')
BASE_FILE = 'demo_sample.json'
NEW_FILES = ['demo_sample_ican.json', 'demo_sample_internet.json', 'demo_sample_challenge.json']

BAD_WORDS = ['AI 生成', 'AI生成', '人工智能生成', '大模型生成']


def load(fn):
    with open(os.path.join(STATIC, fn), encoding='utf-8') as f:
        return json.load(f)


def main():
    base = load(BASE_FILE)
    base_data_keys = set(base['data'].keys())
    print('BASE data 字段数：%d' % len(base_data_keys))
    print()

    ok_all = True
    for fn in NEW_FILES:
        p = os.path.join(STATIC, fn)
        print('=' * 66)
        print('FILE %s' % fn)
        try:
            d = load(fn)
            print('  JSON_OK  True')
        except Exception as e:
            print('  JSON_OK  False -> %s' % e)
            ok_all = False
            continue
        data = d['data']
        prop = data.get('proposal') or ''
        n = len(prop)
        cn = len(re.findall(r'[\u4e00-\u9fff]', prop))
        print('  字节数    %d B' % os.path.getsize(p))
        print('  proposal  字符数 %d（其中汉字 %d）  >=8000: %s' % (n, cn, n >= 8000))
        if n < 8000:
            ok_all = False
        # 字段差集
        mine = set(data.keys())
        miss = base_data_keys - mine
        extra = sorted(mine - base_data_keys)
        print('  字段差集(base-mine) %s  差集为空: %s' % (sorted(miss) if miss else '[]', not miss))
        print('  我方多出的字段      %s' % extra)
        if miss:
            ok_all = False
        # 顶层
        print('  顶层字段  %s' % list(d.keys()))
        print('  _demo=%r  _demo_note=%r  rating=%r' % (d.get('_demo'), d.get('_demo_note'), d.get('rating')))
        # 评分自洽
        js = data.get('judge_scores') or []
        s = sum((it.get('score') or 0) * (it.get('weight') or 0) / 100.0 for it in js)
        w = sum((it.get('weight') or 0) for it in js)
        print('  评分：维度 %s' % '、'.join('%s %s%%×%s' % (it['name'], it['weight'], it['score']) for it in js))
        print('        加权合计 %.2f (round=%d)  权重合计 %s%%  字段 score=%s  一致: %s'
              % (s, round(s), w, data.get('score'), round(s) == data.get('score')))
        if round(s) != data.get('score'):
            ok_all = False
        sc = data.get('scores') or {}
        s2 = sum((v.get('score') or 0) * (v.get('weight') or 0) / 100.0 for v in sc.values())
        print('        scores 字典加权 %.2f  与 score 一致: %s' % (s2, round(s2) == data.get('score')))
        print('        dims 长度 %d  judge_scores 长度 %d  scores 长度 %d' %
              (len(data.get('dims') or []), len(js), len(sc)))
        # 富媒体
        print('  rich_charts %d  rich_tables %d  deck slides %d' %
              (len(data.get('rich_charts') or []), len(data.get('rich_tables') or []),
               len(((data.get('rich_deck') or {}).get('slides')) or [])))
        for c in data.get('rich_charts') or []:
            print('    chart id=%-9s url前缀=%s  长度%d' % (c.get('id'), (c.get('url') or '')[:30], len(c.get('url') or '')))
        print('  顶层 rich_charts/tables/deck 与 data 内一致: %s' %
              ((d.get('rich_charts') == data.get('rich_charts')) and
               (d.get('rich_tables') == data.get('rich_tables'))))
        # 团队
        tm = data.get('team_members') or []
        print('  团队 %d 人：%s' % (len(tm), '、'.join('%s(%s)' % (m['name'], m['major']) for m in tm)))
        # 红线
        hit = [w2 for w2 in BAD_WORDS if w2 in prop]
        print('  红线「AI 生成」字样：%s' % (hit if hit else '未出现'))
        if hit:
            ok_all = False
        # 抽查
        print('  one_liner：%s' % data.get('one_liner'))
        print('  proposal 前 80 字：%s' % prop[:80].replace('\n', ' '))
        print()

    print('=' * 66)
    print('三份 one_liner 互不相同：%s' %
          (len(set(load(f)['data']['one_liner'] for f in NEW_FILES)) == 3))
    print('三份 proposal 前 80 字互不相同：%s' %
          (len(set(load(f)['data']['proposal'][:80] for f in NEW_FILES)) == 3))
    print('总判定：%s' % ('ALL_OK' if ok_all else 'HAS_ISSUE'))


if __name__ == '__main__':
    main()
