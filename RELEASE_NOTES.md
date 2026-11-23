# Mihomo Lite v0.4.0

Traffic statistics, latency charts, a live IP monitor and a rebuilt Proxies page.

## English

### New

- **Traffic page** - live speeds, session and daily totals, a rolling 2-minute chart,
  per-direction today stats and a reset button.
- **Latency fluctuation chart** on the dashboard: last 60 samples for the current node
  with average and jitter.
- **Dashboard rework** - current node, latency, session usage, LAN IP, a live public-IP
  monitor (60 s refresh) and Rule / Global / Direct outbound switching.
- **Proxies page rebuilt** - groups as a chip row, one-click node switching, per-node
  latency with jitter, and a single "Test all delays" action.
- **QR-code import** for subscriptions and inline YAML (image file, decoded locally).
- **Force stop core** button with proxy restore, for when the core misbehaves.
- Subscription downloads now negotiate with Clash-style User-Agents and accept
  base64-wrapped profiles; link-list providers get a clear explanation.

### Reliability and security

- Core and wintun downloads are pinned and SHA-256 verified; both ship in the package.
- GitHub Actions pinned by commit SHA; release tag passed via env (no shell injection).
- Binaries removed from git; wintun GPL-2.0 notice and licence text added.
- Core output is written to the log, startup timeout raised to 45 s, crash messages
  include the last core line.
- Native focus rectangles removed from the sidebar and list widgets.

### Install

`MihomoLite-Setup-0.4.0-x64.exe` or `MihomoLite-v0.4.0-portable-x64.zip`,
Windows 10/11 x64. The installer is not code-signed yet.

## 中文

### 新增

- **流量页**：实时速度、本次与今日总量、最近 2 分钟滚动曲线、今日上下行分开统计、一键重置。
- **延迟波动图**：首页显示当前节点最近 60 次采样，附均值与抖动。
- **首页重做**：当前节点、延迟、本次用量、内网 IP、公网 IP 动态监测（60 秒刷新），
  以及 Rule / Global / Direct 出站模式切换。
- **代理页重构**：顶部代理组标签、单击切节点、节点延迟带波动、一键"全部测延迟"。
- **二维码导入**：支持订阅与内联 YAML，图片本地解码。
- **强制结束内核**按钮：同时恢复系统代理，内核异常时可一键止损。
- 订阅下载自动使用 Clash 风格 User-Agent 协商，支持 base64 包裹的配置；
  对只返回链接列表的服务商给出明确说明。

### 可靠性与安全

- 内核与 wintun 固定版本并做 SHA-256 校验，均随包分发。
- GitHub Actions 按 commit SHA 固定；发布 tag 改为环境变量传递。
- 二进制移出 Git；补充 wintun GPL-2.0 声明与许可全文。
- 内核输出写入日志文件，启动超时放宽到 45 秒，崩溃提示附最后一行内核输出。
- 去掉侧边栏与列表控件的原生焦点黑框。

### 安装

`MihomoLite-Setup-0.4.0-x64.exe` 或 `MihomoLite-v0.4.0-portable-x64.zip`，
支持 Windows 10/11 x64，安装包暂未签名。
