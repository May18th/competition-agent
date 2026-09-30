# -*- coding: utf-8 -*-
"""249b：质检拦截后导出状态挂起 + 附带「AI 自评」改名（app.js，幂等）

249b 根因（读代码读出来的）：
  exportOne() 开头创建了常驻 loading（ms:0 不会自动关）：
      window.__wbExportLoading = wbToast('正在生成「…」文件…', {type:'info', ms:0});
  但函数里有三处提前 return 都没关它：
      ① _DOM_TO_KEY[id]==='proposal' && !wbExportTargetOk()   → 直接 return
      ② !text.trim()  → 弹「没有内容」后 return
      ③ !r.ok → await wbExportError(...) 后 return   ← 质检拦截（422 一票否决）走这条
  而 finally 里只恢复了按钮（btn.disabled/innerHTML）和清了 _qcTimer，
  唯独没关 toast。质检打回时用户看到的就是「正在生成…」永久挂起，
  再点其它导出也没反应（看着像整块导出卡死）。
修法：把关闭 loading 收进 finally，一处兜底覆盖所有退出路径。
"""
import io, os

BASE = '/opt/comp-agent'
JS = os.path.join(BASE, 'static', 'app.js')
out = []
s = io.open(JS, 'r', encoding='utf-8').read()
orig = s

# ---------- 1. exportOne 的 finally：补关 loading ----------
OLD_FIN = """            } finally {
                if (_qcTimer) clearTimeout(_qcTimer);
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }"""
NEW_FIN = """            } finally {
                if (_qcTimer) clearTimeout(_qcTimer);
                // 249b：常驻 loading 必须在这里兜底关掉。
                // 上面三条提前 return（目标串号 / 无内容 / 质检拦截 !r.ok）
                // 都不会走到成功分支的显式关闭，漏关就是「正在生成…」永久挂起，
                // 用户会以为整块导出卡死。失败路径统一由 finally 收尾。
                if (window.__wbExportLoading) {
                    try { wbToastClose(window.__wbExportLoading); } catch (e) {}
                    window.__wbExportLoading = null;
                }
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }"""
n1 = s.count(OLD_FIN)
if n1:
    s = s.replace(OLD_FIN, NEW_FIN)
    out.append('249b exportOne finally 补关 loading ×%d OK' % n1)
else:
    out.append('249b exportOne 未匹配（可能已修）')

# ---------- 2. 打包函数（1162/1172 附近）同样兜底 ----------
OLD_PACK = """            } finally {
                if (window.__wbExportLoading) { wbToastClose(window.__wbExportLoading); window.__wbExportLoading = null; }
"""
if OLD_PACK in s:
    out.append('249b 打包函数已有兜底关闭（跳过）')
else:
    out.append('249b 打包函数：未找到现成兜底，需人工确认（现按已有逻辑，见复查项）')

# ---------- 3. 附带：「AI 自评」→「智能自评」（308b 同一条规避 AI 字样的规矩）----------
c1 = s.count('AI 自评')
c2 = s.count('AI自评')
if c1 or c2:
    s = s.replace('AI 自评', '智能自评').replace('AI自评', '智能自评')
    out.append('文案：「AI 自评」改名 ×%d（含无空格 ×%d）' % (c1, c2))
else:
    out.append('文案：无「AI 自评」残留')

if s != orig:
    io.open(JS, 'w', encoding='utf-8').write(s)
    out.append('app.js 写入完成')

# 复查
s2 = io.open(JS, 'r', encoding='utf-8').read()
out.append('复查 AI自评残留=%d' % (s2.count('AI 自评') + s2.count('AI自评')))
out.append('复查 finally 兜底在=%s' % ('常驻 loading 必须在这里兜底关掉' in s2))
print('\n'.join(out))
