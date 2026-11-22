# Mihomo Lite v0.3.0

First feature-complete milestone: bilingual UI, node speed test, public IP check,
a smaller package and a faster start.

## English

### Highlights

- **English / 中文 UI** - switch the whole interface in Settings (restart to apply).
- **Node speed test** - pick a Selector node and measure real download throughput through it;
  the previous selection is restored afterwards.
- **Public IP check** - see the IP your traffic actually exits from, queried through the proxy.
- **Lighter and faster** - unused Qt translations dropped (dist 170.7 -> 164 MB), pages are
  built lazily (cold start ~4.25 -> 3.3 s).
- **Log copy/export** with secrets redacted, live node filter, connect on launch.
- **Keyboard focus is visible again**, and Dependabot keeps dependencies current.

### Reliability carried in this line

Elevated TUN restart no longer races the single-instance lock; the uninstaller restores the
system proxy before removing files; TUN failures surface as warnings instead of a green light;
subscription tokens are redacted; updated active profiles reload live.

### Install

`MihomoLite-Setup-0.3.0-x64.exe` or `MihomoLite-v0.3.0-portable-x64.zip`,
Windows 10/11 x64. The installer is not code-signed yet.

## 中文

### 本版重点

- **中英文界面**：在设置里切换整个界面语言（重启生效）。
- **节点测速**：选中 Selector 组的节点后测真实下载带宽，测完自动恢复原来的选择。
- **公网 IP 检测**：看出流量实际从哪个 IP 出去，请求走本地代理。
- **更轻更快**：不再打包未使用的 Qt 翻译（包体 170.7 → 164 MB），页面懒加载
  （冷启动约 4.25 → 3.3 秒）。
- **日志复制/导出**（自动脱敏）、节点实时过滤、启动即连接。
- **恢复键盘焦点边框**；引入 Dependabot 维护依赖。

### 这一版包含的可靠性修复

提权重启不再与单实例锁冲突；卸载前会恢复系统代理；TUN 启动失败会给出警告而不是绿灯；
订阅 token 已脱敏；活动配置更新后可热重载。

### 安装

`MihomoLite-Setup-0.3.0-x64.exe` 或 `MihomoLite-v0.3.0-portable-x64.zip`，
支持 Windows 10/11 x64，安装包暂未签名。
