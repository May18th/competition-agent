# WorkBuddy 回执 · 419 轮（手机打不开 / DNS 与证书）

时间：2026-09-30 03:4x
执行：W（WorkBuddy），全程在源站 8.149.236.90 实测，证据为命令输出，非推测。

---

## 一、重要更正：419 的根因判断是错的，「装 certbot / Let's Encrypt」这条不要执行

419 原文说「源站无 443 证书（nginx 无 ssl 配置、/etc/ssl 无正式证书）——HTTPS 完全依赖 Cloudflare 边缘」。
**实测反证如下**：

| 检查项 | 实测结果 |
|---|---|
| nginx 443 server 块 | **存在**，`server_name kechuang2026.cn www.kechuang2026.cn`，`listen 443 ssl` |
| 源站证书文件 | `/etc/nginx/kechuang2026.cn.pem` + `.key`（Sep 28）**存在** |
| 证书主体/签发 | `CN=kechuang2026.cn`，DigiCert Inc（Encryption Everywhere DV TLS CA - G2），**非自签** |
| 证书 SAN | `DNS:kechuang2026.cn, DNS:www.kechuang2026.cn` |
| 有效期 | notBefore Sep 27 2026 → **notAfter Dec 25 2026**（未过期） |
| 绕过 DNS 直连源站 443 | `curl --resolve kechuang2026.cn:443:8.149.236.90 https://kechuang2026.cn/api/health` → **200**；`/` → **200** |

结论：**源站 HTTPS 完全健康，证书有效且到年底才过期。问题 100% 在 DNS 层（走了 Cloudflare 代理），不在源站。**

因此：
- **不要跑 `certbot --nginx`**。certbot 会重写 nginx 的 443 块，可能把现在这份能用的 DigiCert 配置改坏，且在 DNS 仍指 CF 的情况下 HTTP-01 验证必然失败（CF 返回 301）。
- 419 里「安装证书」这一步应整体作废，只保留「DNS 改灰云」。

## 二、实测确认的 DNS 现状（需要域名持有人处理）

```
dig +short kechuang2026.cn        → 104.21.63.156 / 172.67.147.62   (Cloudflare)
dig +short www.kechuang2026.cn    → 172.67.147.62 / 104.21.63.156   (Cloudflare)
dig +short AAAA kechuang2026.cn   → 2606:4700:3034::ac43:933e
                                    2606:4700:3033::6815:3f9c       (Cloudflare IPv6，确实存在)
curl http://kechuang2026.cn/api/health → 301  (CF 代理接管)
```

**待办（Cloudflare 控制台，需账号持有人操作）**：
1. A 记录 `kechuang2026.cn → 8.149.236.90`：橙色云朵点成**灰色（DNS only）**；
2. A 记录 `www → 8.149.236.90`：同样点灰；
3. **删除 AAAA 记录**（已实测存在两条 CF IPv6，留着会打到 2606:4700:: 导致验证失败）；
4. TTL 设 60 秒。
5. 生效判据：`dig +short kechuang2026.cn` **只剩 8.149.236.90**，`curl http://kechuang2026.cn/api/health` 返回 **200**（不再是 301）。

> 我没有 Cloudflare 控制台凭据，这一步必须由你（或 Codex 有账号权限时）操作。

## 三、我已在服务器侧完成的救急改动：kcwx.online 配成完整 HTTPS 站点

**发现的问题**：原 nginx 只有 `kechuang2026.cn` 的 443 块，**没有 `kcwx.online` 的 server 块** → `kcwx.online` 落到 default_server → 下发的是 `kechuang2026.cn` 的证书 → **域名不匹配，浏览器弹证书警告**。
而 `kcwx.online` 的 DNS **已经是直连源站**（8.149.236.90），不经过 CF，国内手机能直连阿里云。

**已做**：
- 新增 `/etc/nginx/sites-available/comp-agent` 末尾追加 `server_name kcwx.online www.kcwx.online` 的 443 块，用源站已有的 `/etc/nginx/kcwx.online.pem`（CN=kcwx.online，DigiCert，有效期至 2026-12-23）；
- 备份：`/etc/nginx/sites-available/comp-agent.bak.20260930_kcwx`；
- `nginx -t` 通过 → `systemctl reload nginx`；
- 配置文件原件：`/opt/comp-agent/nginx_kcwx443.conf`。

**验证（服务器实测）**：
```
kcwx.online:443 下发证书 subject → CN = kcwx.online   (原为 CN = kechuang2026.cn，已修正)
curl https://kcwx.online/            → 200   (未加 -k，严格校验证书通过)
curl https://kcwx.online/api/health  → 200
首页 ?v= 版本号                       → 35 处全 v=20260930e
```

**意义**：`kcwx.online` 现在是**不经过 Cloudflare、证书合法、可直接访问**的入口，手机 4G 应当能打开。**明天演示建议直接用这个域名兜底**，不必等 kechuang2026.cn 的 DNS 生效。

## 四、没能验证的项（如实说明）

- **手机 4G 真机实测**：我手边没有手机，也没法模拟 4G 网络，kcwx.online 在手机上到底能不能开**我没验证过**。以上是源站侧证据（DNS 直连 + 证书合法 + HTTP 200），推断应可访问，但不等同于真机通过。需要你手机关 wifi 实测一次。
- **kechuang2026.cn 灰云切换后的效果**：未发生切换，无法验证。

## 五、当前线上版本号

`v=20260930e`（35 处），含 417（智能辅助声明）、418（AI 字样清理 22 处）、415（防白屏/下载降级）、412（logo 接线）。
