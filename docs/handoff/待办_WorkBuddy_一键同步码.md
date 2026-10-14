# 待办_WorkBuddy_一键同步码（不登录跨设备）

> 来源：Codex 后端（2026-09-28）
> 对象：WorkBuddy（index.html 归你）
> 优先级：P1（轻量跨设备同步，评委零摩擦）

## 后端接口（已实现，待部署）

- `GET /api/sync_code` → `{success, sync_code}`（8 位短码，如 `AB3K7M2P`）
- `POST /api/bind_uid` body `{code}` → `{success, bound:true}` / `{success:false, error}`

原理：绑定后当前设备的匿名 uid 换成目标 uid，历史自动归到同一份。不登录、不用密码。

## 前端要做

1. 历史面板加一个轻量「同步」入口：
   - 显示本机同步码（调 `/api/sync_code`）；
   - 提供输入框「输入别的设备同步码」→ 调 `/api/bind_uid` → 成功后重拉 `/api/history`。
2. **赛前不露用户名密码登录/注册入口**（后端已留，前端不接就行）。
3. 同步码展示做成可一键复制，别让用户手抄 8 位码。

## 验证

- 设备 A 显示同步码 → 设备 B 输入 → B 能看到 A 的历史；
- 同步码无效给提示；
- 首页没有用户名密码登录入口。
