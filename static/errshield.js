/* 前端错误护盾：任何未捕获的 JS 错误 / Promise 拒绝都显式上屏，
   避免老内核浏览器「整页空白无提示」。不依赖任何外部库。 */
(function () {
  function show(msg) {
    try {
      var el = document.getElementById('wbErrShield');
      if (!el) {
        el = document.createElement('div');
        el.id = 'wbErrShield';
        el.style.cssText = 'position:fixed;left:8px;right:8px;bottom:8px;z-index:99999;' +
          'max-height:50vh;overflow:auto;background:#3b0d0d;color:#ffd7d7;' +
          'border:1px solid #ff6b6b;border-radius:10px;padding:10px 12px;' +
          'font:13px/1.6 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;' +
          'box-shadow:0 8px 24px rgba(0,0,0,.35)';
        (document.body || document.documentElement).appendChild(el);
      }
      el.textContent = '⚠ 页面脚本报错（请把这段发我）：\n' + msg;
    } catch (e) {}
  }
  window.addEventListener('error', function (e) {
    var m = e && e.message ? e.message : 'unknown error';
    if (e && e.filename) m += '\n@ ' + e.filename + ':' + (e.lineno || 0);
    show(m);
  });
  window.addEventListener('unhandledrejection', function (e) {
    var r = e && e.reason;
    show('Promise 拒绝:  `+ (r && r.message ? r.message : (r ? String(r) : 'unknown')));
  });
})();
