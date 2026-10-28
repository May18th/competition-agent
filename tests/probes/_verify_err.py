# -*- coding: utf-8 -*-
"""端到端验证：stage 通道 + 402 友好错误（当前 DeepSeek 余额不足，正好是真场景）"""
import json, time, urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def post(path, payload):
    r = urllib.request.Request('http://127.0.0.1:8080' + path,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json'}, method='POST')
    return json.load(opener.open(r, timeout=180))
def get(path):
    return json.load(opener.open('http://127.0.0.1:8080' + path, timeout=60))

print("=== ① 提交异步任务 ===")
r = post('/api/generate_async', {
    "competition_name": "iCAN大学生创新创业大赛",
    "idea": "校园二手书智能循环平台",
    "mode": "fast", "proposal_draft": ""
})
tid = r.get('task_id')
print("task_id =", tid)

print("\n=== ② 立刻查 status（应能看到 stage 字段）===")
s = get('/api/status/' + tid)
print("status =", s.get('status'), "| stage =", s.get('stage'))

print("\n=== ③ 轮询到终态 ===")
for _ in range(60):
    time.sleep(2)
    s = get('/api/status/' + tid)
    if s.get('status') != 'running':
        break
print("status =", s.get('status'), "| stage =", s.get('stage'))
print("error  =", s.get('error'))
print("detail =", str(s.get('detail'))[:150])
