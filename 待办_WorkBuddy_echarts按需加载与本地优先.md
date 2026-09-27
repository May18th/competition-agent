# 待办_WorkBuddy_echarts 按需加载与本地优先

> 来源：Codex 后端审计（2026-09-28）
> 对象：WorkBuddy（index.html 归你）
> 优先级：P1（性能 + 国内可访问性）

## 背景与现状

index.html 目前 echarts 是「首屏即加载 + CDN 优先」：

```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<script>window.echarts || document.write('<script src="/static/echarts.min.js"><\/script>');</script>
```

问题：
1. jsdelivr 在大陆经常被墙/慢，用户是国内大学生，等于首屏白等外网。
2. 本地已有 `/static/echarts.min.js`（nginx gzip 后约 332KB），但现在 CDN 优先、本地只是 document.write 兜底，顺序反了。
3. echarts 只在「图表」tab / 生成后图表区用到，不该首屏就拉 1MB。

## 要求

1. **本地静态优先**：直接加载 `/static/echarts.min.js`，去掉 jsdelivr CDN 这一路（或降级为备用），避免外网依赖。
2. **按需加载**：echarts 在「图表」tab 首次渲染、或首次需要画图时再动态注入 `<script>` 并等待就绪，之前不要阻塞首屏。
3. 保留现有 `typeof echarts === 'undefined'` 的 no-op 兜底，保证图表加载失败时页面不崩。

## 验证

- 首屏 HTML/静态请求里不再有 jsdelivr 的 echarts 请求；
- 打开「图表」tab 能正常出图；
- 断网 / 外网 CDN 不可用时，本地 static 仍能出图（或优雅降级不崩）。

## 说明

- `/static/` 有 30 天缓存，若改 static 文件需改名或加版本后缀（之前交接里提醒过）。
