# -*- coding: utf-8 -*-
"""限流加固探针（2026-11-25 巡检后补）。

背景：线上实测发现两个可组合的绕过——
  ① `_client_ip()` 直接取 X-Forwarded-For 首地址，而 nginx 用
     $proxy_add_x_forwarded_for（追加），客户端伪造的值正好排第一；
  ② 限流键优先用 cookie uid，清掉 cookie 就重置计数。
两者叠加，匿名请求可以无限刷模型额度。

本文件锁住修复后的行为：
  - 公网对端发来的 X-Real-IP / X-Forwarded-For 一律不采信
  - 本机反代（127.0.0.1）转发的 X-Real-IP 采信
  - 限流是 uid 桶 + IP 桶双桶，任一超限即拒
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import app as appmod  # noqa: E402  （根目录转发垫片 → backend.app）


class ClientIpTest(unittest.TestCase):
    """_client_ip 只信本机反代写入的 X-Real-IP。"""

    def test_public_peer_ignores_both_headers(self):
        """公网对端自己发的 XFF / X-Real-IP 全部无效。"""
        with appmod.app.test_request_context(
                '/', headers={'X-Forwarded-For': '1.2.3.4', 'X-Real-IP': '5.6.7.8'},
                environ_overrides={'REMOTE_ADDR': '203.0.113.9'}):
            self.assertEqual(appmod._client_ip(), '203.0.113.9')

    def test_local_proxy_trusts_real_ip(self):
        """本机 nginx 转发的 X-Real-IP 采信。"""
        with appmod.app.test_request_context(
                '/', headers={'X-Real-IP': '198.51.100.7'},
                environ_overrides={'REMOTE_ADDR': '127.0.0.1'}):
            self.assertEqual(appmod._client_ip(), '198.51.100.7')

    def test_local_proxy_without_real_ip(self):
        """本机转发但没带 X-Real-IP 时退回 remote_addr。"""
        with appmod.app.test_request_context(
                '/', environ_overrides={'REMOTE_ADDR': '127.0.0.1'}):
            self.assertEqual(appmod._client_ip(), '127.0.0.1')

    def test_local_proxy_ignores_forwarded_for(self):
        """即便来自本机，XFF 也不采信（只认 X-Real-IP）。"""
        with appmod.app.test_request_context(
                '/', headers={'X-Forwarded-For': '1.2.3.4'},
                environ_overrides={'REMOTE_ADDR': '127.0.0.1'}):
            self.assertEqual(appmod._client_ip(), '127.0.0.1')


class DualBucketTest(unittest.TestCase):
    """限流为 uid 桶 + IP 桶，任一超限即拒。"""

    def setUp(self):
        appmod._rate_hits.clear()

    def tearDown(self):
        appmod._rate_hits.clear()

    def _ctx(self, uid, ip):
        return appmod.app.test_request_context(
            '/', headers={'X-Real-IP': ip},
            environ_overrides={'REMOTE_ADDR': '127.0.0.1'})

    def test_same_uid_blocked_after_limit(self):
        with self._ctx('u1', '203.0.113.1'):
            for _ in range(3):
                self.assertFalse(appmod._rate_limited('probe', 3, 60))
            self.assertTrue(appmod._rate_limited('probe', 3, 60))

    def test_rotating_cookie_still_blocked_by_ip_bucket(self):
        """核心回归：换 uid 绕不过 IP 桶。"""
        # ip_limit 设成 5，模拟 uid 一直换、IP 不变
        blocked = 0
        for i in range(8):
            with self._ctx('u%d' % i, '203.0.113.2'):
                if appmod._rate_limited('probe2', 3, 60, ip_limit=5):
                    blocked += 1
        self.assertGreaterEqual(blocked, 3, '换 cookie 绕过了限流')

    def test_spoofed_xff_does_not_open_new_bucket(self):
        """伪造 XFF 不产生新 IP 桶。"""
        results = []
        for i in range(8):
            with appmod.app.test_request_context(
                    '/', headers={'X-Forwarded-For': '10.0.0.%d' % i},
                    environ_overrides={'REMOTE_ADDR': '127.0.0.1'}):
                results.append(appmod._rate_limited('probe3', 3, 60, ip_limit=5))
        self.assertTrue(any(results[5:]), '伪造 XFF 后仍能无限通过')

    def test_different_uid_and_ip_pass(self):
        """不同用户、不同出口互不影响。"""
        for i in range(5):
            with self._ctx('user%d' % i, '198.51.100.%d' % (10 + i)):
                self.assertFalse(appmod._rate_limited('probe4', 3, 60))

    def test_buckets_are_isolated_by_name(self):
        """不同业务共用同一套数据结构但不互相计数。"""
        with self._ctx('u9', '203.0.113.9'):
            for _ in range(3):
                appmod._rate_limited('bizA', 3, 60)
            self.assertTrue(appmod._rate_limited('bizA', 3, 60))
            self.assertFalse(appmod._rate_limited('bizB', 3, 60))


class ProtectedRoutesTest(unittest.TestCase):
    """模型接口都应挂上限流。"""

    def test_all_model_routes_rate_limited(self):
        import io
        import re
        src = io.open(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'app.py'),
                      encoding='utf-8').read()
        lines = src.split('\n')
        must_guard = {
            '/api/chat': 'chat',
            '/api/scorecard/patch': 'scpatch',
            '/api/revise_chapter': 'revise',
            '/api/rewrite_versions': 'rewrite',
            '/api/scorecard': 'scorecard',
            '/api/chat_apply_proofread': 'proofread',
        }
        for route, bucket in must_guard.items():
            idx = next((i for i, l in enumerate(lines)
                        if l.strip().startswith("@app.route('%s'" % route)), None)
            self.assertIsNotNone(idx, '找不到路由 %s' % route)
            # 取函数体开头 40 行
            body = '\n'.join(lines[idx:idx + 40])
            self.assertIn("_rate_limited('%s'" % bucket, body,
                          '%s 没有挂 %s 桶限流' % (route, bucket))


if __name__ == '__main__':
    unittest.main(verbosity=2)
