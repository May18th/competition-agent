# -*- coding: utf-8 -*-
"""上传安全探针（2026-11-25）：zip 炸弹拦截 + 大小文案与常量一致。

docx/xlsx 是 zip 容器，20MB 的上传可以声明解压出几个 GB。
`_check_zip_bomb` 只读中央目录做预检，不真正解压。
"""
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import app as appmod  # noqa: E402


def make_zip(files, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compress) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def make_bomb(total_mb, chunk_mb=1):
    """流式写入 total_mb 的全零数据，压缩后体积极小 —— 构造真实 zip 炸弹。"""
    buf = io.BytesIO()
    chunk = b'\0' * (chunk_mb * 1024 * 1024)
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        with zf.open('bomb.bin', 'w') as f:
            for _ in range(total_mb // chunk_mb):
                f.write(chunk)
    return buf.getvalue()


class ZipBombTest(unittest.TestCase):

    def test_normal_docx_passes(self):
        raw = make_zip({'word/document.xml': b'<w/>' * 100, 'a.txt': b'hello'})
        self.assertIsNone(appmod._check_zip_bomb(raw))

    def test_oversized_unzip_rejected(self):
        """解压后 210MB > 200MB 上限，应拒绝。"""
        raw = make_bomb(210)
        self.assertLess(len(raw), 5 * 1024 * 1024, '炸弹压缩后应该很小')
        msg = appmod._check_zip_bomb(raw)
        self.assertIsNotNone(msg, '210MB 解压量没有被拦下')
        self.assertIn('安全上限', msg)

    def test_just_under_limit_passes(self):
        raw = make_bomb(60)
        self.assertIsNone(appmod._check_zip_bomb(raw))

    def test_broken_zip_rejected(self):
        msg = appmod._check_zip_bomb(b'PK\x03\x04not-a-real-zip')
        self.assertIsNotNone(msg)
        self.assertIn('zip', msg)

    def test_empty_bytes_rejected(self):
        self.assertIsNotNone(appmod._check_zip_bomb(b''))


class UploadCopyTest(unittest.TestCase):
    """大小提示必须跟常量一致，不能一边 20MB 一边提示 10MB。"""

    def test_error_message_uses_constant(self):
        src = io.open(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'app.py'),
                      encoding='utf-8').read()
        self.assertNotIn('"error": "文件过大，最大支持 10MB"', src,
                         '仍有写死 10MB 的提示，与实际常量不一致')
        self.assertIn('_MAX_UPLOAD_BYTES // 1024 // 1024', src,
                      '大小提示没有引用实际常量')


if __name__ == '__main__':
    unittest.main(verbosity=2)
