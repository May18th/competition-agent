#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量验证：429 限流是否按 identity + scope 分桶（不启 Flask，不耗 API）。"""
import time
from collections import deque

# 复刻 app.py 的 _rate_limited 核心逻辑
_RATE_WINDOW_SEC = 60
_RATE_LIMIT = 5
_rate_hits = {}

def _rate_limited(identity, scope="generate"):
    key = (str(identity or "unknown"), str(scope or "generate"))
    now = time.time()
    hits = [t for t in _rate_hits.get(key, []) if now - t < _RATE_WINDOW_SEC]
    if len(hits) >= _RATE_LIMIT:
        _rate_hits[key] = hits
        return True
    hits.append(now)
    _rate_hits[key] = hits
    return False

def burst(identity, scope="generate", n=6):
    blocked = 0
    for i in range(n):
        if _rate_limited(identity, scope):
            blocked += 1
    return blocked

if __name__ == "__main__":
    print("="*60)
    print("429 限流逻辑验证")
    print("="*60)
    # 1) Alice 快速点 6 次 generate，应触发一次限流
    blocked_a = burst("uid_alice", "generate", 6)
    print(f"[1] Alice 连续 generate 6 次 -> 被拦 {blocked_a} 次（期望 >=1）")

    # 2) Alice 已超限后，Bob 第 1 次 generate 应允许 -> 证明按用户隔离
    bob_first_blocked = _rate_limited("uid_bob", "generate")
    print(f"[2] Alice超限后 Bob 第1次 generate -> 被拦 {bob_first_blocked} 次（期望 0，证明按用户隔离）")

    # 3) Alice 切到 rewrite scope，应允许 -> 证明按接口 scope 隔离
    alice_rewrite_blocked = _rate_limited("uid_alice", "rewrite")
    print(f"[3] Alice 切到 rewrite 第1次 -> 被拦 {alice_rewrite_blocked} 次（期望 0，证明按 scope 隔离）")

    # 4) Bob 继续狂点 generate 到第 6 次，也应触发限流（各自 5 次额度）
    for _ in range(4): _rate_limited("uid_bob", "generate")  # 前面已1次，再加4=5
    bob_sixth_blocked = _rate_limited("uid_bob", "generate")
    print(f"[4] Bob 连续 generate 第 6 次 -> 被拦 {bob_sixth_blocked} 次（期望 >=1）")

    ok = blocked_a >= 1 and not bob_first_blocked and not alice_rewrite_blocked and bob_sixth_blocked
    print("\n" + "="*60)
    print("结论：", "PASS" if ok else "FAIL")
    if not ok:
        print("  期望：同账号同 scope 超限拦截，跨账号/跨 scope 不互相污染")
