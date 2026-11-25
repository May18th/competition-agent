"""前端导出契约守卫（静态校验，不需要浏览器）

为什么需要它：
    app.js 已包进 IIFE，对外只暴露 EXPORTS 表里的符号。这张表是手写的 ——
    新增一个被 onclick 调用的函数却忘了加进表里，页面不会报编译错，
    只会在用户点下去的那一刻 ReferenceError。2026-11-25 实测该表漏了 19 个符号，
    其中 openHistory / evSave / wbToastClose 都是核心交互。

判据（任一不满足即失败）：
    ① app.js 必须在 IIFE 内且启用严格模式（作用域真的收口了）
    ② 外部（HTML 属性事件 + 内联脚本 + wbchat/scorecard）引用的每一个 app.js 顶层符号，
       都必须出现在 EXPORTS 表里或由文件内 window.X = 自行挂载
    ③ 反向检查：EXPORTS 表里不许出现 app.js 中根本不存在的名字（拼错即失效）
"""
import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "frontend", "static", "app.js")
INDEX = os.path.join(ROOT, "frontend", "index.html")
WBCHAT = os.path.join(ROOT, "frontend", "static", "wbchat.js")
SCORECARD = os.path.join(ROOT, "frontend", "static", "scorecard-online.js")

# HTML 属性里的事件；只取行首的函数名，`onclick="if (...) ..."` 这类语句开头不算
EVENT_ATTR_RE = re.compile(
    r'on(?:click|change|input|keyup|keydown|focus|blur|submit|dblclick|'
    r'mouseenter|mouseleave|load|error|toggle|dragstart|drop)\s*=\s*["\']?\s*'
    r'([A-Za-z_$][\w$]*)\s*\('
)
KEYWORDS = {"if", "for", "while", "switch", "return", "try", "typeof", "void", "new", "delete"}


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def inline_scripts(html):
    """抽出所有内联 <script> 块（跳过带 src 的外链脚本）"""
    return "\n".join(
        m.group(1)
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    )


def toplevel_decls(app_src):
    """app.js 在 IIFE 内的一层声明（恰好 8 空格缩进）。

    实测声明分布：0 格 1 个（IIFE 外的文件级）、4 格 6 个、**8 格 441 个**（模块顶层，
    这才是契约单元）、12 格 664 个（函数体第一层局部变量，不是契约）、
    16/20/24… 更深的全是局部。原实现用 {4,8} 把 4 格和 8 格都算进来、
    又把 12 格当成契约，才导致 `d` `n` `w` 这类局部变量被误判成「未导出」。
    """
    names = set()
    for m in re.finditer(
        r"^[ \t]{8}(?:async\s+)?(?:function|var|let|const)\s+([A-Za-z_$][\w$]*)",
        app_src, re.M
    ):
        names.add(m.group(1))
    return names


def exports_table(app_src):
    """解析 var EXPORTS = { k: k, ... } 的键集合"""
    m = re.search(r"var EXPORTS\s*=\s*\{([\s\S]*?)\};", app_src)
    if not m:
        return None
    pairs = re.findall(r"([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*)", m.group(1))
    return {k for k, v in pairs if k == v}


def self_mounted(app_src):
    """文件内 window.X = ... 自行挂载的符号"""
    return set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=(?!=)", app_src))


def strip_comments(src):
    """去掉 // 行注释、/* */ 块注释和 <!-- --> HTML 注释。

    注释里提到某个名字不构成跨文件依赖。实测：index.html 的一段说明文字里
    写了 `_streamAccum`，它就被当成「内联脚本依赖 app.js 的 _streamAccum 却
    没导出」——而 `_streamAccum` 是 app.js 的内部状态，本来就不该导出。
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", " ", src, flags=re.M)
    src = re.sub(r"[ \t]//[^\n]*", " ", src)
    return src


def identifiers(src):
    """提取可能是"变量引用"的标识符。

    必须排除四类噪声，否则会产生大量假依赖：
      - 属性访问 d.total、obj.total
      - 字符串/CSS 类名片段 wbsc-total
      - 注释（见 strip_comments）
      - 字符串字面量内容
    """
    src = strip_comments(src)
    # 抹掉字符串字面量内容，保留引号以免把前后标识符粘连
    src = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", src)
    src = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', src)
    src = re.sub(r"`(?:[^`\\]|\\.)*`", "``", src, flags=re.S)
    out = set()
    for m in re.finditer(r"(?<![\w$.-])([A-Za-z_$][\w$]*)(?![\w$-])", src):
        name = m.group(1)
        # 前一个字符不是 . 已经由 lookbehind 保证；再挡掉连字符后缀
        if name in ("true", "false", "null", "undefined", "this"):
            continue
        out.add(name)
    return out


def shadowed_locals(src):
    """内联脚本里被局部声明的名字。

    首页内联脚本里 `var at = ...`、`function box(...)` 这类局部量，
    和 app.js 的顶层同名符号是两回事 —— 不构成跨文件依赖。
    """
    names = set()
    names |= set(re.findall(r"\bvar\s+([A-Za-z_$][\w$]*)", src))
    names |= set(re.findall(r"\blet\s+([A-Za-z_$][\w$]*)", src))
    names |= set(re.findall(r"\bconst\s+([A-Za-z_$][\w$]*)", src))
    names |= set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", src))
    # var a = 1, b = 2 形式
    for m in re.finditer(r"\bvar\s+([^;\n]+)", src):
        for part in m.group(1).split(","):
            n = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
            if n:
                names.add(n.group(1))
    # 函数参数
    for m in re.finditer(r"function\s*[\w$]*\s*\(([^)]*)\)", src):
        for p in m.group(1).split(","):
            n = re.match(r"\s*([A-Za-z_$][\w$]*)", p)
            if n:
                names.add(n.group(1))
    # 单字母/双字母短名基本是循环变量与临时量，误报概率高且不可能是跨文件契约
    names |= {n for n in re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]{0,2})(?![\w$])", src)}
    return names


class FrontendExportContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = read(APP)
        cls.index = read(INDEX)
        cls.chat = read(WBCHAT)
        cls.sc = read(SCORECARD)
        cls.decls = toplevel_decls(cls.app)
        cls.table = exports_table(cls.app)
        cls.mounted = self_mounted(cls.app)
        cls.inline = inline_scripts(cls.index)

    # ---------- ① 作用域确实收口 ----------
    def test_iife_and_strict_mode(self):
        head = "\n".join(self.app.splitlines()[:20])
        self.assertIn("'use strict'", head, "app.js 顶部必须启用严格模式")
        self.assertRegex(head, r"\(function\s*\(\s*\)\s*\{", "app.js 必须包在 IIFE 内")

    def test_export_table_exists(self):
        self.assertIsNotNone(self.table, "未找到 EXPORTS 表")
        self.assertGreater(len(self.table), 50, "EXPORTS 表条目过少，疑似被截断")

    # ---------- ② 外部引用必须都能解析 ----------
    def test_html_event_handlers_are_exported(self):
        """HTML 里 onclick="foo(...)" 的 foo 必须对外可见"""
        names = {n for n in EVENT_ATTR_RE.findall(self.index) if n not in KEYWORDS}
        owned = names & self.decls
        missing = sorted(owned - self.table - self.mounted)
        self.assertEqual(
            missing, [],
            "这些函数被 HTML 事件调用，但既不在 EXPORTS 表里也没有 window 挂载：%s" % missing
        )

    def test_app_generated_handlers_are_exported(self):
        """app.js 自己拼 onclick 字符串调用的函数同样要导出（如历史列表项）"""
        names = {n for n in EVENT_ATTR_RE.findall(self.app) if n not in KEYWORDS}
        owned = names & self.decls
        missing = sorted(owned - self.table - self.mounted)
        self.assertEqual(missing, [], "app.js 动态生成的 onclick 目标未导出：%s" % missing)

    def test_inline_script_dependencies_are_exported(self):
        """首页内联脚本对 app.js 的依赖（含 window.X 形式）"""
        ids = identifiers(self.inline) | set(re.findall(r"window\.([A-Za-z_$][\w$]*)", self.inline))
        owned = ids & self.decls
        # 内联脚本自己声明过的同名局部量不算依赖
        missing = sorted(owned - self.table - self.mounted - shadowed_locals(self.inline))
        self.assertEqual(missing, [], "首页内联脚本依赖的符号未导出：%s" % missing)

    def test_sibling_modules_dependencies_are_exported(self):
        """wbchat.js / scorecard-online.js 对主脚本的依赖"""
        ids = identifiers(self.chat) | identifiers(self.sc)
        ids |= set(re.findall(r"window\.([A-Za-z_$][\w$]*)", self.chat + self.sc))
        owned = ids & self.decls
        shadow = shadowed_locals(self.chat) | shadowed_locals(self.sc)
        missing = sorted(owned - self.table - self.mounted - shadow)
        self.assertEqual(missing, [], "同级模块依赖的符号未导出：%s" % missing)

    # ---------- ③ 表里不许有幽灵条目 ----------
    def test_no_ghost_exports(self):
        ghosts = sorted(self.table - self.decls - self.mounted)
        self.assertEqual(ghosts, [], "EXPORTS 表里这些名字在 app.js 中不存在（拼错或已删除）：%s" % ghosts)

    # ---------- ④ 猴补丁目标必须可覆盖 ----------
    def test_monkey_patch_targets_are_exported(self):
        """首页会做 window.renderRich = wrapper 这类包装，这些函数必须在表里，
        且 app.js 内部若有裸名调用，必须写成 (window.X || X)(...) 才能走到包装层。"""
        targets = ["renderRich", "paintPartial", "previewDeckStyle",
                   "streamFinish", "streamPrepare", "wbPickTheme"]
        missing = [t for t in targets if t not in self.table and t not in self.mounted]
        self.assertEqual(missing, [], "猴补丁目标未导出：%s" % missing)

        # 只有"代码里真被调用"的函数才需要改写。
        # 出现在 onclick 字符串里的调用（wbPickTheme）由浏览器按全局查找，不算内部调用。
        for t in targets:
            code_calls = 0
            for line in self.app.splitlines():
                s = line.strip()
                if not s or s.startswith("//") or s.startswith("*") or s.startswith("/*"):
                    continue
                if re.search(r"\bfunction\s+" + re.escape(t) + r"\b", s):
                    continue
                # 跳过含 onclick 的字符串拼接行
                if "onclick" in s or "on" + "change" in s:
                    continue
                if re.search(r"(?<![\w$.])" + re.escape(t) + r"(?=\s*\()", s):
                    code_calls += 1
            if not code_calls:
                continue
            self.assertRegex(
                self.app,
                r"\(window\." + re.escape(t) + r"\s*\|\|\s*" + re.escape(t) + r"\)\s*\(",
                "%s 在代码里被调用 %d 处，但没走 window 查找，首页包装不会生效" % (t, code_calls)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
