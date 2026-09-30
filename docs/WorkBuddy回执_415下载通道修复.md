# WorkBuddy 回执 · 415 轮①「夸克下载无文件」

时间：2026-09-30 04:0x
执行：W（WorkBuddy）｜版本号 **v=20260930f**（35 处全升）｜服务已 restart，health 200

---

## 一、为什么之前不算修好

415 派活要求「改后端真实文件 URL（/api/export_word、/api/export_pdf、/api/export_zip）下载」。
**这条要求按字面做不到**，原因实测如下：

- `export_word` / `export_pdf` / `export_zip` 的路由确实支持 GET，但参数靠 `_export_data_from_request()`
  从 **POST body** 取（`text` 是整篇计划书正文、`charts` 是图表数据），
  GET 的 query string 根本承载不了这么大的 body。
- 所以「前端 a[href=接口URL] 直接 GET」这条路不成立，之前只能做 blob 方案。

我之前那一版只做了「UC 内核探测 + 失败提示」——**等于没修**，因为失败是静默的，
加提示只是告诉用户"你运气不好"，文件照样落不下来。

## 二、这次的做法：blob 回传后端 → 落盘 → 换真实 http URL

不动任何现有导出逻辑（风险最低，且覆盖**全部**导出类型，不止 word/pdf/zip）：

```
前端拿到 blob（原有流程不变）
   ↓  UC/夸克内核才走这条
POST /api/blob_to_url  (multipart: file + name)
   ↓
后端落盘 static/tmpdl/<随机16位>.<白名单扩展名>
   ↓
返回 {"url": "/static/tmpdl/xxx.docx"}
   ↓
前端 a[href=真实URL] + download → 浏览器原生下载器接管
```

真实 http URL 是 UC 内核唯一能稳定落盘的形式。

**改动文件**
- 后端 `app.py`：追加路由 `/api/blob_to_url`（2618 字节，幂等补丁 `fix_415_dlurl.py`）
- 前端 `static/app.js`：
  - 新增 `wbUcDownload(blob, name)`（async，上传换 URL）
  - 原逻辑抽为 `wbSaveBlobFallback()`，保留给 Chrome/Safari/系统浏览器
  - `wbSaveBlob()` 改为分发：UC 内核走新方案，失败才回落
  - 上传期间弹「正在准备文件…」（多一次 1-3 秒往返，不给等待感就又是"点了没反应"）

**安全约束**（都做了，且实测）
- 文件名只取 basename、去掉 `\` `/`，再过滤非法字符 → 防目录穿越
- 扩展名白名单，不在名单内一律落 `.bin`
- 存盘名是随机 token，**不复用用户传的文件名** → 防覆盖、防猜测
- 大小受 Flask `MAX_CONTENT_LENGTH=10MB` 限制，另加显式 10MB 检查
- 每次请求顺带清理 30 分钟前旧文件，总量超 200 删最旧

## 三、实测证据（服务器上跑，非本地推测）

| 场景 | 结果 |
|---|---|
| 正常上传 | `{"name":"ceshi.docx","success":true,"url":"/static/tmpdl/9e647b4f01e24226.docx"}` |
| 取回该文件 | **HTTP 200，SIZE=14，内容 `hello 415 test`**（与上传一致） |
| 目录穿越 `name=../../../../etc/passwd` | 被防住 → 存成 `/static/tmpdl/<随机>.bin`，未越权 |
| 缺 file 字段 | `{"error":"缺少文件字段 file","success":false}` 400 |

线上验证：
- `https://kcwx.online/static/app.js?v=20260930f` HTTP 200，473978 字节
- `wbUcDownload` 命中 3 次、`blob_to_url` 命中 1 次
- 首页 `?v=` 35 处全 `v=20260930f`
- `node --check` 通过、`py_compile` 通过；备份 `app.py.bak.20260930_dlurl`

## 四、没能验证的（如实）

- **夸克真机能否落盘，我依然无法验证**——手边没有夸克浏览器。
  这次相比上一版的进步是：原来失败**完全静默**（不报错、不出文件），
  现在走的是真实 http URL（UC 内核下载器最稳的路径），且失败会回落到原 blob 方案并给提示。
  但「夸克里点一下真的出现文件」这一步，**仍需你真机实测一次**。
- 10MB 以上的导出（如大材料包 zip）会 413，此时回落到 blob 方案——这条路径没实测过。

## 五、给 Codex / 豆包的提示

- 415 的 ②（历史白屏）③（缩放退出）我之前只加了全局 `wbCrashGuard` 兜底，
  **resize 逻辑没动**，因为怕引入新问题。若真机仍有缩放退出，需要专门改 resize 处理。
- 本回执不涉及 415 之外的项。
