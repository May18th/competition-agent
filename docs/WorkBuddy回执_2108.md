# WorkBuddy 回执 · 第一百零八轮（2026-09-28 19:30）

## 已落地（commit dade25b，版本号 v=20260928e 时间戳唯一值 ✅ 铁律合规）

| 项 | 内容 | 验证（CDP 实测） |
|---|---|---|
| 107-1 对比度 | 日间 --text-mute #8490b0(3.18)→#5f6b88(5.32)、--text-dim 保持 #55618a(6.06)；夜间 --text-dim #8491b8(5.94)→#a9b7d9(9.25)、--text-mute #5d6a8c(3.45)→#8b98bd(6.48)。双主题次要文字全部过 AA | CDP 读变量+预计算对比度 ✅ |
| 107-3 主色 | 去靛紫 #4f46e5 → 深青 #0e7490 / 青绿 #0f766e（白字对比 5.36/5.47）；夜间亮版 #38bdf8/#2dd4bf；硬编码旧主色 20+ 处全量替换；line/track/阴影/光晕同步青系 | 生产站实测 --c-a=#0e7490 ✅ |
| 107-4 logo | PIL 程序化重绘 512px：圆角方块（青蓝→青绿→深青渐变）+ 递增柱 + 四角星，与主色同系；16/32/54px 预览可辨 | 生产站 naturalWidth=512 ✅ |
| 106-1 雷达标题 | 标题加 white-space:normal + word-break:keep-all + overflow-wrap:anywhere；克隆测量 300px/328px 容器均不截断 | ✅ |
| 106-2 数字高亮 | app.js 新增 wbHlAll：TreeWalker 只在展示层把「数字+单位」包 .wb-keynum（加粗+主色+浅底），不改 markdown 源（导出件不受影响）；MutationObserver 350ms 防抖覆盖流式/历史/重渲染；幂等（重复跑不叠加）。正则不收裸「年/月」防「2026年」误伤 | 生产站冒烟 3 处命中（21.6万…）✅ |
| 106-3 赛事入口 | 「全部赛事 ▾」→「全部 15 赛 ▾」+ 实底强调（原虚线幽灵按钮与普通 chip 无异）；「共 15 个内置赛事」整行可点展开下拉 | ✅（另修真 bug：hint 点击会被"点外部关闭"监听立即关掉，已把 compCountHint 加进放行名单，实测点行展开 15 项、点别处正常关） |
| 105-2 输入栏 | teamBody（团队成员）从手机折叠列表移除，全端默认展开；文案改「第 3 步 · 团队成员/分工（选填，强烈建议填真人）」 | 桌面+移动 display:block ✅ |
| 版本号 | index.html 引用改 v=20260928e（时间戳唯一）；_wbcheck.py 断言升级为「必须时间戳唯一值，禁 v=N」 | ✅ |

## 静态校验
- `_wbcheck.py` 21/21 PASS（DOM 闭合、8 个内联 script node --check、CSS 括号、id 注释外存活、版本号时间戳）
- app.js node --check OK；CDP 桌面(1280)+移动(390/360) 日/夜 4 组截图无翻车，pageErrors 0

## 部署方式（本次特殊情况）
- 服务器上 Codex 有未提交 app.py（M 状态）→ **没有用 reset --hard**，改为 `git fetch + git checkout origin/main -- index.html static/app.js static/style.css static/logo.png`，按文件落地，app.py WIP 原样保留
- 覆盖前备份：/root/wb_bak_20260928191906/
- 公网验收：首页 200、v=20260928e×2、logo.png 29654B（新版）、app.js 428670B 含 wbHlAll、style.css 85733B 含 0e7490/wb-keynum、health 正常、生产站浏览器实测如上
- 注意：验收中撞到一次 CF 边缘节点吐旧 index.html（数秒后自愈），豆包验收时若看到旧版请强刷或稍后重试

## 遗留 / 提醒
1. 【Codex·阻塞级】105-1 首页常驻反馈入口仍未落地（本轮实测 txtHasFeedback=false）——下周评审前必须上线
2. 【Codex】105-4 失败场景反馈接口可调用性确认
3. 本机 Git Credential Manager 对 push 场景挂死（凭据刷新不走代理被墙），本次改走「bundle → 服务器中转 push」；已留 drive2.mjs（CDP 复用外部 Edge 实例）。下轮如遇 push 卡死可直接走该通道
4. 已知非本轮问题冻结项不变：手机打不开问题按用户指示冻结
