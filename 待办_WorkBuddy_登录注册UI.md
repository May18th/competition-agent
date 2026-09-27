# 待办_WorkBuddy_登录注册 UI

> 来源：Codex 后端（2026-09-28，方案 B 轻量登录）
> 对象：WorkBuddy（index.html 归你）
> 优先级：P1（跨设备看同一份历史）

## 后端接口（已实现，待部署）

- `POST /api/register` body `{username, password}` → `{success, username}` / `{success:false, error}`
- `POST /api/login` body `{username, password}` → 同上
- `POST /api/logout` → `{success:true}`
- `GET /api/me` → `{success, logged_in, username}`

校验规则：用户名 2~32 字符、密码至少 4 位、用户名唯一。登录成功后 cookie 里的匿名 uid 会换成账号 uid，历史自动按账号归集。

## 前端要做

1. 历史面板（或右上角）加「登录 / 注册」入口：
   - 未登录：显示「登录」+「注册」两个输入态（用户名 + 密码）。
   - 已登录：显示「你好，{username}」+「退出」。
2. 注册成功后、登录成功后、退出后，**重新拉一次 `/api/history`**（历史会随账号切换而变化）。
3. 错误用后端返回的 `error` 字段提示，别静默。
4. 入口保持轻量，别抢首页主流程（生成那条线不动）。

## 验证

- 注册 → 生成几篇 → 换设备登录同一账号 → 能看到完整历史；
- 退出后回到匿名，看不到账号历史；
- 错误密码登录被拒并提示。
