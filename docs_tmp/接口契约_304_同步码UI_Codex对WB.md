# 304 双端同步 · 前端同步码 UI 接口契约（Codex → WorkBuddy）

时间：2026-09-29 ｜ 归属：前端 UI = WorkBuddy；后端接口**已存在且已部署，无需改**。

## 一、结论（先看这个）

「桌面切 iCAN→挑战杯，移动端刷新仍 iCAN」的根因是：两个设备各自有不同 `comp_uid` cookie，`/api/user_state` 按 uid 隔离，所以各读各的 state。

但后端**早就做好了跨设备绑定**，就是「一键同步码」：
- `GET /api/sync_code` —— 拿本机同步码
- `POST /api/bind_uid` —— 用同步码把本机绑到另一台设备的 uid（重签 cookie）

绑定后两台设备变成**同一个 uid**，`/api/user_state`、历史、草稿、赛事选择、档位全部共享。**后端一行不用改**，只差前端 UI。

## 二、接口（已上线，契约如下）

### 1) 拿本机同步码
```
GET /api/sync_code
```
响应成功：
```json
{ "success": true, "sync_code": "AB3CD5E7" }
```
响应失败（极少见）：
```json
{ "success": false, "error": "同步码生成失败，请重试" }
```
说明：`sync_code` 是 8 位大写短码，字符集 `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`（无 0/O/1/I）。

### 2) 绑定到另一台设备
```
POST /api/bind_uid
Content-Type: application/json
{ "code": "AB3CD5E7" }
```
响应成功：
```json
{ "success": true, "bound": true }
```
响应失败（缺码）：
```json
{ "success": false, "error": "请输入同步码" }
```
响应失败（码无效）：
```json
{ "success": false, "error": "同步码无效，请检查后重试" }
```

**注意 1**：错误响应也是 HTTP 200，前端要**看 `success` 字段**，别只看状态码。
**注意 2**：`code` 会 `.strip().upper()`，前端传小写也没事；也兼容 form 提交（`application/x-www-form-urlencoded`）。

## 三、前端要做的（WorkBuddy）

1. **展示本机同步码**：进入某处设置/同步入口时 `GET /api/sync_code`，把 `sync_code` 显示出来（可加「复制」按钮）。
2. **输入他人同步码**：一个输入框 + 「绑定」按钮，提交 `POST /api/bind_uid` `{code}`。
3. **绑定成功后**：
   - 提示「已绑定，跨设备同步已开启」；
   - **刷新页面或重新拉一次 `/api/user_state` + 历史**，让新 uid 的 state / 历史 / 草稿生效（cookie 已重签，刷新后就是共享的那份）。
4. **失败处理**：`success:false` 时把 `error` 文案直接展示（「同步码无效，请检查后重试」等），别弹红字堆栈。
5. **演示只读会话**：`/api/bind_uid` 会被只读 403 拦截（演示态本就不需要跨设备同步），前端在 demo 态把同步入口隐藏或置灰即可。

## 四、入口位置建议

放「历史记录 / 设置」附近都行，醒目但不占首屏；移动端放抽屉菜单里。具体位置你定，后端无要求。

## 五、验收标准

1. 设备 A 显示同步码，设备 B 输入该码绑定后刷新，**赛事选择/档位/草稿/历史与 A 一致**。
2. 绑错码（乱输）有友好提示，不报错崩溃。
3. demo 只读态下同步入口不可用（隐藏/置灰），不撞 403。
4. 移动端 + 桌面端都能进同步入口。
