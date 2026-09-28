# 待办_WorkBuddy_点击感反馈（全站可点元素）

> 来源：Codex（2026-09-28，用户需求）
> 对象：WorkBuddy（index.html 归你）
> 优先级：P1（基础可用性，不是花哨特效，与「克制」不冲突）

## 要求

全站所有可点击元素（按钮、卡片、chip、下拉项、tab、图标按钮）都要有**三态反馈**：

1. **hover**：颜色/亮度轻微变化；
2. **active**：按下瞬间 `transform: scale(0.98)` 或 `translateY(1px)` 下沉，松手回弹；
3. **focus**：键盘 Tab 到时可见轮廓（可访问性，不能省）。

## 参数

- 过渡时长 150~200ms，别太长；
- 支持 `prefers-reduced-motion` 时关闭位移动效；
- 触屏端 `:active`（或 touchstart）也要触发，保证手机上点下去也有下沉感。

## 验证

- 桌面 hover/active/focus 三态都有；
- 手机上点按钮有下沉反馈；
- 关闭动画偏好时不位移。
