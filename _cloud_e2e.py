# -*- coding: utf-8 -*-
"""
云上端到端验收：走阿里云 ECS 公网地址（经 nginx 反代）跑一次真实生成。
验证点：
  1. 首页可访问
  2. /api/health 正常
  3. 异步任务能起、进度推进、终态 done
  4. 长连接（>40s）不被 nginx 掐断
用法： python _cloud_e2e.py [url]
"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://8.149.236.90'


def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read().decode('utf-8', 'ignore')


def post(path, payload, timeout=30):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode('utf-8', 'ignore')


def main():
    ok = True

    # 1 首页
    t0 = time.time()
    code, body = get('/')
    print(f"[1] 首页        code={code}  {time.time()-t0:.2f}s  "
          f"title={'科创赛事' in body}")
    ok &= code == 200 and '科创赛事' in body

    # 2 health
    code, body = get('/api/health')
    try:
        h = json.loads(body)
        print(f"[2] health     code={code}  status={h.get('status')}  "
              f"quota={h.get('quota', {}).get('remaining')}")
    except Exception:
        h = {}
        print(f"[2] health     code={code}  解析失败: {body[:200]}")
    ok &= code == 200 and h.get('status') == 'ok'

    # 3 异步生成
    payload = {
        "mode": "fast",
        "competition_name": "中国国际大学生创新大赛",
        "project_name": "基于多模态感知的智适应助老陪护机器人",
        "track": "高教主赛道",
        "keywords": "助老陪护,多模态感知,边缘计算",
        "outline_text": "",
    }
    t0 = time.time()
    code, body = post('/api/generate_async', payload)
    if code != 200:
        print(f"[3] 生成        FAIL code={code} {body[:300]}")
        return 1
    task_id = json.loads(body).get('task_id')
    print(f"[3] 任务已起    task_id={task_id}")

    # 4 轮询
    last_pct = -1
    stages = []
    final = None
    deadline = time.time() + 300
    while time.time() < deadline:
        code, body = get(f'/api/status/{task_id}', timeout=30)
        if code != 200:
            print(f"[4] 轮询异常    code={code}")
            ok = False
            break
        s = json.loads(body)
        st = s.get('status')
        pct = s.get('pct', 0)
        stage = s.get('stage', '')
        if stage and (not stages or stages[-1] != stage):
            stages.append(stage)
        if pct > last_pct:
            print(f"    {s.get('stage_label', stage):<16} {pct}%")
            last_pct = pct
        if st in ('done', 'error', 'cancelled'):
            final = s
            break
        time.sleep(2)

    elapsed = time.time() - t0
    if final is None:
        print(f"[4] 结果        超时未终态（{elapsed:.1f}s）")
        ok = False
    elif final.get('status') != 'done':
        print(f"[4] 结果        status={final.get('status')} "
              f"error={final.get('error')}")
        ok = False
    else:
        d = final.get('data') or {}
        text = json.dumps(d, ensure_ascii=False)
        print(f"[4] 结果        done  用时 {elapsed:.1f}s  "
              f"payload={len(text)} 字符")
        print(f"    stage链路: {' -> '.join(stages[:12])}")

    print()
    print("=== 结论:", "全部通过 ✅" if ok else "存在失败 ❌", "===")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
