# Mihomo Lite v0.2.0

TUN mode and automatic subscription updates, on top of the v0.1 glass client.

## English

### Highlights

- **TUN mode (optional)** - capture all traffic through a virtual adapter instead of the
  Windows system proxy. Three stacks (mixed / system / gVisor), automatic UAC elevation with
  auto-reconnect, and one-click Wintun installation from Settings.
- **Automatic subscription updates** - refresh subscriptions every 1, 3, 6, 12, 24 or 48 hours
  while the app runs. Updates are validated, keep the previous file as a backup, and never
  interrupt an active connection. **Profiles -> Update all** forces a check.
- **Rule checking** - unknown policies, rules after MATCH, missing no-resolve, duplicates and
  undefined rule-providers are reported with line numbers; a final MATCH is added when missing.
- Everything from v0.1: bundled Mihomo core, crash-safe system proxy journal, proxy groups and
  latency tests, live traffic, liquid-glass UI, tray and single-instance guard.

### Notes

- TUN requires administrator rights; the app offers to restart elevated and reconnect.
- Wintun is not bundled (GPL-2.0, upstream project); Settings downloads the official build.
- While TUN is enabled the system proxy is intentionally left untouched.
- The installer is not code-signed yet: SmartScreen may ask for "More info -> Run anyway".

### Install

Download `MihomoLite-Setup-0.2.0-x64.exe`, or the portable
`MihomoLite-v0.2.0-portable-x64.zip`. Windows 10/11 x64.

## 中文

### 本版重点

- **TUN 模式（可选）**：通过虚拟网卡接管全部流量，不再依赖系统代理。支持 mixed / system /
  gVisor 三种栈；需要管理员权限时自动弹 UAC、重启并自动重连；设置里一键安装 Wintun。
- **订阅自动更新**：可设置每 1 / 3 / 6 / 12 / 24 / 48 小时自动更新订阅。更新前校验、保留
  上一份配置、不会打断正在使用的连接；在 **Profiles -> Update all** 可立即检查。
- **规则检查**：策略名拼错、MATCH 之后的死规则、缺 no-resolve、重复规则、未定义的
  rule-provider 都会按行号提示；缺少最终 MATCH 时会自动补一条。
- v0.1 的能力全部保留：内置内核、崩溃安全代理日志、节点切换与测速、实时流量、
  磨砂玻璃界面、托盘与单实例保护。

### 注意事项

- TUN 需要管理员权限，程序会提示重启并以管理员身份自动重连。
- Wintun 不随包分发（GPL-2.0，独立项目），在设置里按需下载官方版本。
- 开启 TUN 时不会改动系统代理，避免两者互相干扰。
- 安装包暂未签名，SmartScreen 可能提示，选择"更多信息 -> 仍要运行"。

### 安装

下载 `MihomoLite-Setup-0.2.0-x64.exe`（安装版）或 `MihomoLite-v0.2.0-portable-x64.zip`
（便携版）。支持 Windows 10/11 x64。
