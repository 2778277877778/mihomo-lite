# Mihomo Lite v0.1.1

A simple, lightweight and reliable Windows client for the Mihomo proxy core,
with a frameless liquid-glass interface.

## English

### What's in the box

- **Bundled core** - an unmodified Mihomo v1.19.33 (GPL-3.0) ships inside the package, so the
  app works offline right after installing. A newer core can be downloaded later from Settings.
- **One-switch connection** - start the core, wait for the local API, enable the Windows system
  proxy, and restore the previous proxy state on disconnect, crash, or next launch.
- **Profiles that stay intact** - local YAML or subscription imports; the original file is never
  edited, updates keep a previous copy, and a hardened runtime copy is generated with a
  localhost-only controller and a fresh random secret.
- **Rule checking** - before connecting, rules are validated (policy typos, rules after MATCH,
  missing no-resolve, duplicates, undefined rule-providers). A final MATCH is added when missing.
- **Proxy control** - groups, node switching, latency tests, live traffic counters.
- **Liquid-glass UI** - frameless rounded window, Windows acrylic blur, dark and light themes,
  tray icon, start with Windows.

### Changes in v0.1.1

- Bilingual README (English + 中文)
- Bilingual release notes and a proper release title
- Version bump to 0.1.1

### Install

1. Download `MihomoLite-Setup-0.1.1-x64.exe` (installer) or
   `MihomoLite-v0.1.1-portable-x64.zip` (portable, no installation).
2. Import a profile, press **Connect**.

Windows 10/11 x64. The installer is not code-signed yet, so SmartScreen may ask for
"More info -> Run anyway".

### Compatibility

The app manages the Windows system proxy. Do not run two clients that both change it at the
same time (for example Clash Verge); disconnect one of them first.

### License

Application code: MIT. Bundled Mihomo core: GPL-3.0, unmodified, source at
https://github.com/MetaCubeX/mihomo/tree/v1.19.33. PySide6 / Qt: LGPL-3.0, dynamically linked.

---

## 中文

### 这个版本包含什么

- **内置内核**：安装包自带未修改的 Mihomo v1.19.33（GPL-3.0），装完即可离线使用；
  之后可在设置里下载更新版本。
- **一键连接**：启动内核、等待本地 API、开启 Windows 系统代理；断开、崩溃或下次启动时
  自动恢复原来的代理设置。
- **配置不被破坏**：本地 YAML 或订阅导入，原始文件永不修改；订阅更新保留上一份副本；
  运行时生成加固副本（只监听 127.0.0.1、每次随机密钥）。
- **规则检查**：连接前校验路由规则（策略名拼错、MATCH 之后的死规则、缺 no-resolve、
  重复规则、未定义的 rule-provider），缺少最终 MATCH 时自动补一条。
- **节点管理**：策略组、节点切换、延迟测试、实时流量。
- **磨砂玻璃界面**：无边框圆角窗口、Windows 亚克力模糊、深浅主题、托盘常驻、开机自启。

### v0.1.1 的改动

- README 改为中英双语
- 发布说明改为中英双语，并补上正式的 Release 标题
- 版本号升级到 0.1.1

### 安装

1. 下载 `MihomoLite-Setup-0.1.1-x64.exe`（安装版）或
   `MihomoLite-v0.1.1-portable-x64.zip`（便携版，免安装）
2. 导入配置，点 **Connect**

支持 Windows 10/11 x64。安装包暂未签名，SmartScreen 可能提示，选择
"更多信息 -> 仍要运行"即可。

### 兼容性提醒

本程序会接管 Windows 系统代理。请不要同时运行两个都会修改系统代理的客户端
（例如 Clash Verge），先断开其中一个。

### 许可证

应用代码 MIT；内置 Mihomo 内核为 GPL-3.0 且未修改，源码见
https://github.com/MetaCubeX/mihomo/tree/v1.19.33；PySide6 / Qt 为 LGPL-3.0，动态链接。
