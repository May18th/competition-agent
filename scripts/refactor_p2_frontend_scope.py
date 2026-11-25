# -*- coding: utf-8 -*-
"""P2：给 app.js 套模块作用域，把全局泄漏收收敛成一张显式导出表。

问题
----
app.js 现在 277 个函数全部落在全局作用域（浏览器实测 `typeof window._wbFetch`
返回 function）。任何第三方脚本、浏览器扩展、甚至页面上另一个 <script> 都能
覆写它们，改一个名字就会在全站静默产生 undefined。同时 8000 行单一文件没有
边界，谁依赖谁只能靠读代码。

本脚本做两件事（都不改函数体）
------------------------------
1. 整个文件包进 IIFE，函数不再自动泄漏到 window。
2. 文件末尾生成一张**显式导出表**，只把「页面确实要用」的符号挂回 window：
   - index.html 内联 on*="" 里调用的 86 个处理器
   - index.html 内联 <script> 里直接调用 / window.xxx 访问的 21 个
   其余全部留在模块内，外部拿不到——这就是收敛。

为什么不拆成多个文件
--------------------
拆文件要处理加载顺序（现在 index.html 只引一个 app.js），一旦顺序错，
某个函数在解析期就被调用会直接 ReferenceError。收敛作用域是零风险的
第一步；拆分留到有构建步骤或 type=module 时再做，那时可以真正 import。

安全性
------
- 只加两层包裹（开头 IIFE、结尾导出），不动任何已有行。
- 导出表用 `window.X = X`，对已有 window.X 的（如 wbChartOpenFull 在
  index.html 定义）不覆盖：只导出本文件**自己定义**的。
- 先写副本验证语法，再落盘。
"""
import io
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'frontend', 'static', 'app.js')
HTML = os.path.join(ROOT, 'frontend', 'index.html')

# 内联 on*="" 用到的处理器（过滤器把 JS 内置方法名排除）
JS_BUILTINS = {
    'cancel', 'click', 'getElementById', 'preventDefault', 'querySelectorAll',
    'reload', 'remove', 'scrollTo', 'stopPropagation', 'var', 'catch', 'forEach',
    'map', 'filter', 'then', 'close', 'bind', 'render', 'done', 'fallback', 'now',
    'setTimeout', 'clearTimeout', 'parseInt', 'parseFloat', 'push', 'slice',
}

HEADER = '''/* app.js —— 主站交互脚本
 * ---------------------------------------------------------------------------
 * 模块作用域：整个文件包在一个 IIFE 里，函数不再泄漏到 window。
 * 页面需要的符号在文件末尾的导出表里显式挂回 window（见 EXPORTS）。
 *
 * 为什么这么做：此前 277 个函数全在全局，任何脚本都能覆写同名函数，
 * 改错一个名字全站静默失效，且无法判断谁依赖谁。收敛后，新增对外能力
 * 必须显式加进导出表——多一步，但依赖关系变成可枚举的。
 * --------------------------------------------------------------------------- */
(function () {
'use strict';

'''

FOOTER_TMPL = '''
/* ===== 导出表：页面（内联 on*="" 与内联 <script>）实际用到的符号 =====
   只列真正跨边界的。新增对外能力请加进这里，否则页面拿不到。
   不覆盖已存在的 window 属性：同名的由 index.html 自己定义（如 wbChartOpenFull）。

   注意不能写成字符串名 + eval(name)：本文件在 IIFE + 'use strict' 里，
   严格模式的 eval 拿不到外层作用域，eval 会找不到函数。这里直接引用标识符。 */
var EXPORTS = {%s};
for (var _k in EXPORTS) {
    if (Object.prototype.hasOwnProperty.call(EXPORTS, _k) &&
            typeof window[_k] === 'undefined') {
        window[_k] = EXPORTS[_k];
    }
}

})();
'''


def collect_exports(js, html):
    """算出需要挂回 window 的符号集合。"""
    handlers = set()
    for m in re.finditer(r'on(?:click|change|input|submit|focus|blur|keyup|keydown|load|mouseover|mouseout|error)="([^"]*)"', html):
        for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
            handlers.add(c.group(1))

    defined = set(re.findall(r'function\s+([A-Za-z_$][\w$]*)\s*\(', js))
    defined |= set(re.findall(r'(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function', js))

    # 内联 <script> 直接调用 + window.xxx 访问
    cross = set()
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.S):
        body = m.group(1)
        for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', body):
            cross.add(c.group(1))
    cross |= set(re.findall(r'window\.([A-Za-z_$][\w$]*)', html))

    wanted = (handlers | cross) - JS_BUILTINS

    # 第三种：app.js 自己用字符串拼 HTML 时写进去的内联 on*=""。
    # 这类最容易被漏掉——名字只在 JS 字符串里出现，index.html 搜不到，
    # 收敛作用域后按钮点了没反应，且不报错（实测漏了 evDelSection /
    # evToggleSections / coachNext / coachEnd 四个）。
    for m in re.finditer(r'on(?:click|change|input|submit|focus|blur|keyup|keydown|load|mouseover|mouseout|error)="\'?\s*\+\s*[^"\']*?'
                         r'on(?:click|change|input|submit|focus|blur|keyup|keydown|load|mouseover|mouseout|error)=\\?"([^"\\]*)', js):
        for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
            wanted.add(c.group(1))
    for m in re.finditer(r'on(?:click|change|input|submit|focus|blur|keyup|keydown|load|mouseover|mouseout|error)=\\?"([^"\\]*)\\"', js):
        for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
            wanted.add(c.group(1))
    for m in re.finditer(r"""on(?:click|change|input|submit|focus|blur|keyup|keydown|load|mouseover|mouseout|error)='([^']*)'""", js):
        for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
            wanted.add(c.group(1))
    for m in re.finditer(r'on(?:click|change|input|submit|focus|blur|keyup|keydown|load|mouseover|mouseout|error)="([^"]*)"', js):
        for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
            wanted.add(c.group(1))

    return sorted((wanted - JS_BUILTINS) & defined)


def main():
    apply = '--apply' in sys.argv
    js = io.open(APP, encoding='utf-8', newline='').read()
    html = io.open(HTML, encoding='utf-8', newline='').read()
    eol = '\r\n' if '\r\n' in js else '\n'

    if 'app.js —— 主站交互脚本' in js:
        raise SystemExit('已经包过 IIFE，不要重复执行')

    exports = collect_exports(js, html)
    print('需导出的符号: %d' % len(exports))
    for i in range(0, len(exports), 6):
        print('  ' + ', '.join(exports[i:i + 6]))

    body = js
    # 原文件开头有多余空行，去掉后统一由 HEADER 接管
    body = body.lstrip('\r\n')
    new = HEADER.replace('\n', eol) + body.rstrip('\r\n') + eol + \
        FOOTER_TMPL.replace('\n', eol) % ',\n    '.join('%s: %s' % (e, e) for e in exports)

    if not apply:
        out = os.path.join(ROOT, '_app_preview.js')
        io.open(out, 'w', encoding='utf-8', newline='').write(new)
        print()
        print('dry-run：预览写到 %s（%d 行）' % (out, len(new.split('\n'))))
        return 0

    ts = time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(APP, '%s.bak.%s' % (APP, ts))
    io.open(APP, 'w', encoding='utf-8', newline='').write(new)
    print()
    print('已写入。备份：%s.bak.%s' % (APP, ts))
    return 0


if __name__ == '__main__':
    sys.exit(main())
