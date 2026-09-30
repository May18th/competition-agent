# -*- coding: utf-8 -*-
"""249b 补：打包函数的 finally 同样漏关常驻 loading（质检拦截 !r.ok 那条 return 走不到成功分支的关闭）"""
import io, os

BASE = '/opt/comp-agent'
JS = os.path.join(BASE, 'static', 'app.js')
s = io.open(JS, 'r', encoding='utf-8').read()
orig = s

OLD = """            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }
        function _fallbackCopy("""
NEW = """            } finally {
                // 249b：与 exportOne 同一个坑 —— 「打包」被质检打回时走的是
                // if (!r.ok) { await wbExportError(...); return; }，
                // 不会到成功分支那句关闭，常驻 loading 就永久挂起。
                if (window.__wbExportLoading) {
                    try { wbToastClose(window.__wbExportLoading); } catch (e) {}
                    window.__wbExportLoading = null;
                }
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }
        function _fallbackCopy("""

if OLD in s:
    s = s.replace(OLD, NEW, 1)
    io.open(JS, 'w', encoding='utf-8').write(s)
    print('249b 打包函数 finally 补关 loading OK')
elif '249b：与 exportOne 同一个坑' in s:
    print('已修过，跳过')
else:
    print('!! 未匹配打包函数 finally 锚点')
