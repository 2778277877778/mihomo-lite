# Mihomo Lite 可行性评估

> 评估时间：2026-11-07 · 环境：Windows x64 / Python 3.12.10 / 实测机器已安装 Clash Verge Rev
> 所有结论均来自本机真实执行，不是纸面推断。复现脚本见 `tools/smoke/`。

## 结论速览

| 维度 | 判定 | 说明 |
| --- | --- | --- |
| 技术可行性 | **可行（高）** | 核心链路全部实测通过，无自研网络协议需求 |
| 工期可行性 | **可行** | 4 周做出 V0.1 属合理区间，风险集中在系统代理与异常恢复 |
| 体积/性能 | **可行，需裁剪** | 全量 PySide6 达 647 MB，必须改用 Essentials |
| 许可证 | **需先决策** | mihomo 实际为 GPL-3.0，直接影响"是否内置内核" |
| 与现有客户端共存 | **高风险点** | 本机已有客户端占用 7897 与系统代理 |

## 一、实测通过的部分

### 1. 依赖栈（已在 `.venv` 安装并验证）

```
python 3.12.10
PySide6 6.12.0 / Qt 6.12.0      QApplication 可创建
pydantic 2.14.3                 httpx 0.28.1
websockets 17.4                 PyYAML 6.0.3
pytest 9.2.0 / pytest-qt 4.5.0  ruff 0.17.4 / PyInstaller 6.22.3
```

Python 3.14 虽为本机默认版本，但生态适配风险高，选用 3.12 更稳（3.13 亦可）。

### 2. Mihomo 内核全链路（关键验证）

下载 `mihomo-windows-amd64-v1.19.33.zip`（22.5 MB，解压 58.4 MB）后以最小配置启动：

```
REST GET /version   -> {"meta":true,"version":"v1.19.33"}
REST GET /configs   -> mixed-port=17890, mode=rule
REST GET /proxies   -> 7 个代理对象，GLOBAL 组存在
经 127.0.0.1:17890 访问 gstatic  -> HTTP 204（转发真实可用）
WS  /traffic?token=... -> {"up":131,"down":127,"upTotal":131,"downTotal":127}
```

**这意味着 V0.1 的全部技术假设成立**：进程可启动、API 可鉴权、代理可转发、流量可实时订阅。

### 3. Windows 系统代理 API

用 `wininet.dll` 的 `InternetQueryOptionW/InternetSetOptionW`（INTERNET_OPTION_PER_CONNECTION_OPTION=75）实测：

```
查询成功 -> flags=3(DIRECT|PROXY), proxy=127.0.0.1:7897, bypass=<local>
幂等写回成功 -> 证明写入路径可用，且未改变用户既有状态
```

注意：ctypes 必须显式声明 `argtypes/restype`，否则 64 位下指针截断导致调用静默失败（第一次试验即踩到）。

## 二、必须正视的风险

### R1. 与现有客户端争夺系统代理（最高优先级）

本机现状：

```
clash-verge (PID 3684) + verge-mihomo (PID 17992) 正在运行
系统代理 ProxyEnable=1, ProxyServer=127.0.0.1:7897
```

普通用户很可能同时装了别的客户端。若本应用直接改写系统代理而不做检测，会出现：
用户关掉本应用 → 代理指向已退出内核 → **全局断网**。

对策（全部纳入 V0.1）：

1. 启动时记录"接管前快照"（ProxyEnable / ProxyServer / ProxyOverride / AutoConfigURL + 是否由他方持有）。
2. 若检测到代理已指向其他本机端口且该端口存活，弹窗要求用户确认接管。
3. 退出/崩溃恢复时**只恢复自己写过的值**，绝不覆盖他人的新状态（用 journal 比对）。
4. 单实例锁（QLockFile），禁止双开抢端口。
5. 端口冲突检测：7890/7891/7897/9090 被占用时自动改随机高位端口，而不是硬失败。

### R2. 许可证（影响发布形态，须先定）

- mihomo `Alpha` 分支 LICENSE = **GPL-3.0**；GitHub API 显示的 MIT 与实际文件不一致（master 分支显示 "Copyright 2023 KT"）。**必须以具体 release tag 附带的 LICENSE 为准**，不能依赖 API。
- PySide6 = **LGPLv3**（动态链接 + 允许替换即合规；PyInstaller onefile 会把 Qt 打进单文件，法务上更建议 onedir + 独立 DLL）。
- Clash Verge Rev 自身是 GPL-3.0，正是因为它内置了 GPL 内核。

三条可选路径：

| 方案 | 应用许可 | 安装包 | 代价 |
| --- | --- | --- | --- |
| A. 不内置内核，首次运行用户确认后下载 | 可保持 MIT | 约 60–80 MB | 首次启动需联网，体验略差 |
| B. 内置内核 | 应用需 GPL-3.0 并附源码 | 约 120–160 MB | 需提供对应源码/书面要约 |
| C. 内核单独发压缩包 | 应用可 MIT | 最小 | 用户需手动放置 |

建议：**V0.1 走 A**（先跑通体验），正式发布前按法务结论再定 B/C。

### R3. 体积与"轻量"定位

实测：全量 `PySide6` 目录 647.1 MB（含 WebEngine/PDF/Addons/3D）；内核 58.4 MB。

- 只装 `PySide6-Essentials` 实测 **208.9 MB**，且 `QtWidgets/QSystemTrayIcon/QMenu/QLocalServer/QLockFile/QProcess` 全部可用（已用独立 venv 验证），V0.1 功能不需要 Addons。
- 用 PyInstaller `--onedir` + 排除未用模块，预计成品 90–130 MB，安装包 45–70 MB。
- **不要用 onefile**：首启解压慢、杀软误报率高，与"轻量可靠"定位冲突。
- 安装包用 Inno Setup（免费、脚本化、支持卸载清理系统代理）。

### R4. PyInstaller 与杀软

Qt + Python 打包产物常被误报。对策：代码签名证书（后期）、提交误报、发布 SHA256、GitHub Release 附校验说明。

### R5. 其他已识别但可控的点

- **WebSocket 与 Qt 事件循环**：不要引入 qasync 加重依赖；用独立线程跑 asyncio loop，`Signal` 回主线程。websockets 17.4 已验证可用。
- **API 暴露面**：内核只绑 `127.0.0.1`，每次启动生成 32 字节随机 secret，日志中脱敏，配置校验拒绝 `0.0.0.0`。
- **配置安全**：订阅 YAML 里可能含 `external-controller`、`tun`、`dns` 等危险项，生成运行配置时必须覆写白名单字段，不能原样透传。
- **TUN**：不做。需要管理员权限/虚拟网卡/服务，与 V0.1 范围冲突，且极易残留路由。
- **异常恢复**：journal 文件（原代理快照 + pid + 时间戳）在启动时检测；pid 已死则自动还原。

## 三、工期复核

| 阶段 | 内容 | 估时 | 风险 |
| --- | --- | --- | --- |
| 第 1 周 | 骨架 + QProcess + 日志 | 4–5 天 | 低 |
| 第 2 周 | 配置校验/生成 + REST API | 5 天 | 中（配置项差异大） |
| 第 3 周 | 系统代理 + 状态机 + 托盘 | 5–7 天 | **高（R1）** |
| 第 4 周 | 测试 + 打包 + CI | 4–5 天 | 中（杀软/体积） |

按业余投入，4 周偏紧但可达；建议把"系统代理 + 崩溃恢复"单独留 1 周缓冲。

## 四、建议的落地调整

1. 依赖改为 `PySide6-Essentials`（已用独立 venv 验证：Widgets/Tray/QProcess/QLockFile/QLocalServer 均可用，体积 647→209 MB）。
2. 把"端口/代理占用检测"提升为 P0 功能，而不是事后补丁。
3. 许可证先决策再打包，不要默认内置内核。
4. 系统代理的自动化测试用**可注入的注册表后端**（内存 fake），真实注册表只在手测/虚拟机跑，避免 CI 改坏环境。
5. 发布形态：onedir + Inno Setup，附 SHA256 与卸载清理逻辑。

## 五、结论

**技术路线成立，可以按原计划进入 V0.1 开发。**

真正的难点不在"能不能启动 Mihomo"，而在三件事：

1. 系统代理的接管与恢复（尤其与其他客户端共存）；
2. 配置透传带来的安全边界；
3. 分发形态（GPL 内核 + Qt 体积 + 杀软误报）。

这三点在架构里已经预留位置，属于工程细节而非方向性障碍。

## 附：本次验证脚本

- `tools/smoke/config.yaml` —— 最小可运行内核配置
- `tools/smoke/probe.py` —— REST / 代理 / WebSocket 三合一探针
- `tools/smoke/wininet_probe2.py` —— 系统代理 API 幂等读写探针
