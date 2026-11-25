# -*- coding: utf-8 -*-
"""前端作用域收敛的静态守卫（2026-11-25）。

背景：app.js 曾把 277 个函数全放在全局作用域，任何脚本都能覆写同名函数，
改错一个名字全站静默失效。现在整个文件包在 IIFE 里，只有文件末尾 EXPORTS
表里的符号挂回 window。

这个探针不启浏览器，只用正则核对三件事——都是踩过的坑：

1. **内联处理器必须在导出表里**。index.html 的 on*="" 与 app.js 自己用字符串
   拼出来的 on*=""，两处都要覆盖。漏了不报错，只是按钮点了没反应
   （实测漏过 evDelSection / evToggleSections / coachNext / coachEnd 四个）。
2. **导出表不能写成字符串名 + eval(name)**。IIFE 里是严格模式，eval 拿不到
   外层作用域，会静默失败。
3. **内部函数不该出现在 window 上**。收敛的意义就在这；如果某个内部实现
   也被导出，说明清单加宽了，要能发现。
"""
import io
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP_JS = os.path.join(ROOT, "frontend", "static", "app.js")
INDEX_HTML = os.path.join(ROOT, "frontend", "index.html")

EVENT_ATTR = r'on(?:click|change|input|submit|focus|blur|keyup|keydown|load|mouseover|mouseout|error)'
JS_BUILTINS = {
    "cancel", "click", "getElementById", "preventDefault", "querySelectorAll",
    "reload", "remove", "scrollTo", "stopPropagation", "var", "catch", "forEach",
    "map", "filter", "then", "close", "bind", "render", "done", "fallback", "now",
    "if", "return", "function", "typeof", "JSON", "Object", "Array", "String",
}


def read(p):
    return io.open(p, encoding="utf-8").read()


class FrontendScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = read(APP_JS)
        cls.html = read(INDEX_HTML)

    # ---------- 1. 文件确实被包进 IIFE ----------
    def test_app_js_is_wrapped_in_iife(self):
        self.assertIn("(function () {", self.js,
                      "app.js 没包 IIFE，函数会重新泄漏到全局")
        self.assertIn("'use strict';", self.js)
        self.assertTrue(self.js.rstrip().endswith("})();"),
                        "app.js 结尾不是 IIFE 收口，文件可能被截断")
        self.assertIn("var EXPORTS = {", self.js,
                      "找不到导出表，页面将拿不到任何处理器")

    # ---------- 2. 导出机制不能依赖 eval ----------
    def test_export_table_does_not_use_eval(self):
        # 只看导出表本身（var EXPORTS = { 到 for 循环之间），且排除注释行
        m = re.search(r"var EXPORTS = \{.*?\};", self.js, re.S)
        self.assertIsNotNone(m, "解析不到导出表")
        table = "\n".join(l for l in m.group(0).splitlines()
                          if not l.strip().startswith(("/*", "*", "//")))
        self.assertNotIn("eval(", table,
                         "导出表用了 eval()：严格模式下的 IIFE 拿不到外层作用域，会静默失败")
        # 导出表必须是「名字: 同名标识符」的直接引用
        pairs = re.findall(r'([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*)', table)
        self.assertTrue(pairs, "导出表格式不是 name: name")
        bad = [k for k, v in pairs if k != v]
        self.assertEqual([], bad, "这些导出项的值不是同名标识符：%s" % bad)
        self.assertIn("EXPORTS[_k]", self.js[-4000:])

    # ---------- 3. index.html 的内联处理器全部在导出表里 ----------
    def test_all_inline_handlers_are_exported(self):
        exported = self._exported_names()
        missing = []
        for m in re.finditer(EVENT_ATTR + r'="([^"]*)"', self.html):
            for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
                name = c.group(1)
                if name in JS_BUILTINS:
                    continue
                if self._defined_in_js(name) and name not in exported:
                    missing.append(name)
        self.assertEqual([], sorted(set(missing)),
                         "这些处理器被 index.html 调用但没导出，点了会没反应：%s"
                         % sorted(set(missing)))

    # ---------- 4. app.js 自己拼的内联处理器也要导出 ----------
    def test_handlers_generated_inside_app_js_are_exported(self):
        exported = self._exported_names()
        missing = []
        for m in re.finditer(EVENT_ATTR + r'="([^"]*)"', self.js):
            for c in re.finditer(r'\b([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
                name = c.group(1)
                if name in JS_BUILTINS:
                    continue
                if self._defined_in_js(name) and name not in exported:
                    missing.append(name)
        self.assertEqual([], sorted(set(missing)),
                         "app.js 运行时拼出的内联处理器没导出：%s" % sorted(set(missing)))

    # ---------- 5. 内部实现不应被导出 ----------
    def test_internal_helpers_are_not_exported(self):
        exported = self._exported_names()
        # 挑几个确定只被内部调用、页面从不碰的
        internals = ["_wbFetch", "coachStart", "coachShow", "coachNext"]
        # coachNext 是弹层按钮的内联处理器，属于合法导出；其余不该出现
        for name in ["_wbFetch", "coachStart", "coachShow"]:
            self.assertNotIn(name, exported,
                             "%s 是内部函数，不该挂到 window 上" % name)

    # ---------- 辅助 ----------
    def _exported_names(self):
        m = re.search(r"var EXPORTS = \{(.*?)\};", self.js, re.S)
        self.assertIsNotNone(m, "解析不到导出表")
        return set(re.findall(r'([A-Za-z_$][\w$]*)\s*:', m.group(1)))

    def _defined_in_js(self, name):
        return re.search(r'(?:function\s+%s\s*\(|(?:var|let|const)\s+%s\s*=\s*'
                         r'(?:async\s+)?function)' % (re.escape(name), re.escape(name)),
                         self.js) is not None


if __name__ == "__main__":
    unittest.main(verbosity=2)
