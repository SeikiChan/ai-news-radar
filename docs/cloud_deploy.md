# 上云部署指南（24/7 独立运行 + 手机访问）

本文把 AI News Radar 部署成一个**始终在线、带密码、HTTPS、手机可访问**的私人研究终端。
你电脑关机也不影响它运行。

---

## 0. 先认清一个现实：数据源的云适配性

| 数据 | 来源 | 云上表现 |
|---|---|---|
| 期权 gamma / strike / IV | CBOE 延迟全链 | ✅ 正常（交易所公开接口，不限 IP） |
| 暗盘卖空占比 | FINRA 日度文件 | ✅ 正常（监管 CDN） |
| 财务 / 13F / 8-K | SEC EDGAR | ✅ 正常（政府数据） |
| 个股价格 / VIX / 短仓% / 板块 | Yahoo Finance | ⚠️ **数据中心 IP 会被频繁限流（429）** |

> 你的**核心差异化数据全部在云上正常工作**。受影响的只有 Yahoo 那几路。
> 系统已对此做了三层缓解：图表抓取重试 3 次自愈、限流时明示"稍后重试"而非伪造、
> 不缓存限流失败。即便如此，云上 Yahoo 仍会偶尔抖动——见第 4 节的彻底解法。

---

## 1. 必须先设密码（已内置强制）

服务器**拒绝在非 localhost 接口上无密码启动**——这是防裸奔的硬保护。
部署时必须设两个环境变量：

```
AI_NEWS_RADAR_PASSWORD=<一个强密码>
AI_NEWS_RADAR_USER=admin            # 可选，默认 admin
```

访问时浏览器会弹出登录框（HTTP Basic）。配合 HTTPS（第 2、3 节平台自带）即安全。

---

## 2. 推荐路径 A：Fly.io（最省事，有持久卷 + 自动 HTTPS）

适合：想要"几条命令搞定、自动 HTTPS、数据不丢"。约 $0–3/月（小规格常在免费额度内）。

```powershell
# 1. 安装 flyctl 并登录
#    https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# 2. 在项目根目录初始化（会读取 Dockerfile，先不要部署）
cd C:\Users\Allen\ai-news-radar
fly launch --no-deploy
#   - App name: 自取，如 my-news-radar
#   - 选离你近的区域（如 hkg 香港 / nrt 东京）
#   - 不需要数据库 / Redis

# 3. 创建持久卷（保存 FINRA 缓存 / IV 历史 / 诊断归档），1GB 足够
fly volumes create radar_data --size 1 --region hkg

# 4. 设密码（密文存储，不进代码）
fly secrets set AI_NEWS_RADAR_PASSWORD=换成你的强密码

# 5. 部署
fly deploy
```

在 `fly.toml` 里确认两件事（`fly launch` 通常已生成，缺则补上）：

```toml
[[mounts]]
  source = "radar_data"
  destination = "/app/data"

[http_service]
  internal_port = 8765
  force_https = true
  auto_stop_machines = false   # 关键：保持常驻，定时扫描才会跑
  min_machines_running = 1
```

部署完成后访问 `https://<你的app名>.fly.dev`，手机浏览器加书签即可。

---

## 3. 推荐路径 B：小型 VPS（最可控，可加代理彻底解决 Yahoo 限流）

适合：想完全掌控、未来要接住宅代理、或习惯 Linux。约 $4–6/月
（Hetzner CX22 / DigitalOcean / Vultr）。

```bash
# 在一台 Ubuntu 22.04+ VPS 上：

# 1. 装 Docker
curl -fsSL https://get.docker.com | sh

# 2. 拉代码（或 git clone 你的仓库）
git clone https://github.com/SeikiChan/ai-news-radar.git
cd ai-news-radar

# 3. 构建镜像
docker build -t ai-news-radar .

# 4. 跑起来（持久化 data/，设密码，重启自恢复）
docker run -d --name radar --restart unless-stopped \
  -p 8765:8765 \
  -e AI_NEWS_RADAR_PASSWORD='换成你的强密码' \
  -v radar_data:/app/data \
  ai-news-radar
```

**加 HTTPS**（VPS 不自带，用 Caddy 一行搞定，自动签发证书）：

```bash
# 需要一个指向 VPS IP 的域名，如 radar.yourdomain.com
sudo apt install -y caddy
echo 'radar.yourdomain.com {
    reverse_proxy localhost:8765
}' | sudo tee /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

之后 `https://radar.yourdomain.com` 即可，证书自动续期。

---

## 4. 彻底解决 Yahoo 限流（可选，按需再做）

如果云上 Yahoo 抖动让你烦，从轻到重三档：

1. **接受现状**：核心数据（gamma/暗盘/财务/13F）不受影响；价格/VIX 偶尔显示
   "稍后重试"，刷新即可。对隔夜决策影响很小。
2. **住宅代理**（VPS 路线适用）：给 Yahoo 那几路走住宅代理（如 IPRoyal、
   Bright Data，几美元/月）。需要在 `relative_strength._fetch_text` /
   `market_structure` 的 Yahoo 请求上加 proxy——这块要我改代码时再说。
3. **换价格源**：把价格/VIX 从 Yahoo 切到 Stooq（对云 IP 友好）等免费源。
   工作量中等，需要我适配解析。

> 我的建议：先按第 1 档上线，用一周看 Yahoo 抖动到底多影响你，再决定要不要做 2/3。

---

## 5. 部署后自检清单

- [ ] 打开 `https://...` 弹出登录框（说明鉴权生效）
- [ ] 输对密码进入，简报/诊断/财报都能加载
- [ ] 诊断一只票，确认 gamma/strike/暗盘有数据（这些云上应稳定）
- [ ] 关掉你自己的电脑，手机再访问一次——仍能用 = 真正独立运行
- [ ] 隔一天回来看，`data/` 里的诊断归档还在 = 持久卷生效

---

## 6. 成本与维护一句话总结

| 路径 | 月成本 | HTTPS | 持久化 | 维护难度 |
|---|---|---|---|---|
| Fly.io | $0–3 | 自动 | 卷 | 低 |
| VPS + Caddy | $4–6 | 自动 | 卷 | 中（但最可控） |

两条路代码完全一样（同一个 Dockerfile + 密码机制），区别只在托管平台。
先用 Fly.io 跑通；哪天要接住宅代理对抗限流，再迁到 VPS 也只是换个地方 `docker run`。
