# -*- coding: utf-8 -*-
"""
415 轮 ①·补强：夸克 / UC 内核「下载无文件」修复 —— 后端落盘换真实 URL 通道。

背景：
  export_word / export_pdf 等导出接口是 POST + JSON body（正文文本太大走不了 GET），
  返回的是文件流，前端用 blob URL + a[download] 触发下载。
  夸克 / UC 内核（UCBrowser/UCWEB/Quark）对 blob 下载是**静默失败**：
  弹「该网页请求打开外部应用」→ 点了没反应，文件管理和通知栏都没有文件，且不报错。

解法（不改任何现有导出逻辑，风险最低）：
  前端把已拿到手的 blob 回传到本接口 → 后端落盘到 static/tmpdl/<随机名>.<ext>
  → 返回真实 http URL → 前端用 a[href=真实URL] 交给浏览器原生下载器。
  真实 URL 是 UC 内核唯一能稳定落盘的形式。

安全约束：
  - 文件名只取 basename，去掉路径分隔符，再过滤非法字符（防目录穿越）；
  - 扩展名走白名单，不在白名单内一律落为 .bin；
  - 存盘文件名是随机 token，不复用用户传入的名字（防覆盖、防猜测）；
  - 单次请求大小受 Flask MAX_CONTENT_LENGTH(10MB) 限制，另加显式检查；
  - 每次请求顺带清理 30 分钟前的旧文件，且总量超 200 个时删最旧的。
"""
import os
import re
import io

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.py')

MARK = '_WB_DLURL_415'

CODE = '''

# ===== 415 轮 ①·补强（2026-09-30）：夸克 / UC 下载通道 =====
# 夸克/UC 内核对 blob URL + a[download] 静默失败（弹「请求打开外部应用」后不落文件）。
# 前端把已生成的文件回传，后端落盘并返回真实 http URL，由浏览器原生下载器接管。
_WB_DLURL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'tmpdl')
_WB_DLURL_EXTS = {'docx', 'doc', 'pdf', 'zip', 'pptx', 'ppt', 'txt', 'md',
                  'xlsx', 'xls', 'png', 'jpg', 'jpeg', 'html', 'json'}
_WB_DLURL_MAX_BYTES = 10 * 1024 * 1024


def _wb_dlurl_cleanup(max_age_sec=1800, max_files=200):
    """清理过期/过量临时下载文件，避免磁盘被慢慢堆满。"""
    try:
        if not os.path.isdir(_WB_DLURL_DIR):
            return
        now = time.time()
        items = []
        for fn in os.listdir(_WB_DLURL_DIR):
            fp = os.path.join(_WB_DLURL_DIR, fn)
            if os.path.isfile(fp):
                items.append((os.path.getmtime(fp), fp))
        items.sort()
        for mt, fp in items:
            if now - mt > max_age_sec:
                try:
                    os.remove(fp)
                except Exception:
                    pass
        rest = [f for f in os.listdir(_WB_DLURL_DIR)
                if os.path.isfile(os.path.join(_WB_DLURL_DIR, f))]
        if len(rest) > max_files:
            for mt, fp in items[:len(rest) - max_files]:
                try:
                    os.remove(fp)
                except Exception:
                    pass
    except Exception:
        pass


@app.route('/api/blob_to_url', methods=['POST'])
def wb_blob_to_url():
    """把前端已生成的 blob 落盘成真实文件，返回可原生下载的 http URL。"""
    try:
        f = request.files.get('file')
        if not f:
            return jsonify({'success': False, 'error': '缺少文件字段 file'}), 400
        if (request.content_length or 0) > _WB_DLURL_MAX_BYTES:
            return jsonify({'success': False, 'error': '文件超过 10MB 上限'}), 413

        raw = (request.form.get('name') or 'download.bin').strip()
        # 只取文件名本体，去掉一切路径分隔符，再过滤非法字符（防目录穿越）
        base = os.path.basename(raw).replace('\\\\', '_').replace('/', '_')
        base = re.sub(r'[^\\w\\u4e00-\\u9fa5.\\-]', '_', base) or 'download.bin'
        ext = (base.rsplit('.', 1)[-1] if '.' in base else 'bin').lower()
        if ext not in _WB_DLURL_EXTS:
            ext = 'bin'

        os.makedirs(_WB_DLURL_DIR, exist_ok=True)
        fn = uuid.uuid4().hex[:16] + '.' + ext
        f.save(os.path.join(_WB_DLURL_DIR, fn))
        _wb_dlurl_cleanup()
        return jsonify({'success': True, 'url': '/static/tmpdl/' + fn, 'name': base})
    except Exception as e:
        print('[blob_to_url] 失败：%s' % e)
        return jsonify({'success': False, 'error': str(e)}), 500
# ===== 415 轮 ①·补强 结束 =====
'''


def main():
    with io.open(APP, 'r', encoding='utf-8') as fh:
        src = fh.read()

    # 幂等判据用「函数是否已存在」，不能用注释里的 MARK——
    # 第一版把 MARK 只写在脚本变量里、没写进生成的代码，重跑会静默重复追加一整段。
    if 'def wb_blob_to_url' in src:
        print('SKIP: 补丁已存在（幂等，不重复打）')
        return

    with io.open(APP, 'a', encoding='utf-8') as fh:
        fh.write(CODE)

    with io.open(APP, 'r', encoding='utf-8') as fh:
        new = fh.read()

    print('APPENDED_BYTES=%d' % (len(new) - len(src)))
    print('MARK_HIT=%d' % new.count(MARK))
    print('ROUTE_HIT=%d' % new.count("/api/blob_to_url"))
    print('FUNC_HIT=%d' % new.count('def wb_blob_to_url'))
    print('CLEANUP_HIT=%d' % new.count('def _wb_dlurl_cleanup'))


if __name__ == '__main__':
    main()
