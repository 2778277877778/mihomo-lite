# Mihomo Lite v0.5.1

Optional accelerated downloads, with both features off by default.

## English

### What changed

- **Fix: connection could stall on machines with a system/registry proxy.** The loopback
  controller client did not disable environment proxies, so httpx routed `127.0.0.1` API
  requests through the WinINET proxy and never saw the core become ready. The client now
  bypasses the system proxy, matching the other local-only transports.
- **New Downloads page.** Ordinary single-threaded downloads still work exactly as before: pick
  a URL and a save path, and the file goes through the local Mihomo mixed port.
- **Multi-threaded download (optional, off by default).** A HEAD probe checks the size and
  `Accept-Ranges`; when ranges are supported the file is split into 4-16 automatically sized
  segments (manual override available), preallocated and written at each segment offset, so no
  final merge is needed. Idle workers split the longest remaining segment. Failed segments are
  retried with exponential backoff (up to 5 attempts). Segment progress, ETag and
  Last-Modified are kept in a sidecar state file, so an interrupted download resumes; if the
  server's validators changed, it starts over.
- **Multi-node parallel (optional, off by default; requires multi-threaded).** Nodes can be
  selected across subscriptions and profiles. The runtime copy (never the imported profile)
  gets one `mixed` listener per selected node, bound to `127.0.0.1` on a free port. Each
  listener is pinned to its node, so the downloader never asks the controller to switch nodes.
  The page shows per-node speed and status; a failed node is marked abnormal and its unfinished
  segments are reassigned. If several egresses receive HTTP 403/429, concurrency is reduced and
  the download falls back to a single node with a visible notice.
- **Safe by default.** With both switches off, the runtime config is byte-for-byte the same as
  before: no listeners, no extra proxies, no download scheduler. Enabling or disabling the
  switches while connected regenerates and reloads the runtime copy through the existing
  controller; disconnected users are asked to reconnect.
- **Clearer entry points and profile list.** The Downloads page now explains that the Settings
  switches only enable acceleration and provides a button to open/download settings; Settings
  has an **Open Downloads page** button. The Profiles page uses glass cards with active and
  selected badges, so several subscriptions are easy to scan. Minimizing to the tray shows a
  notification; turn off **Minimise to the tray** in Settings -> Application to keep the window
  on the taskbar.
- **Clear core verification result.** **Settings -> Mihomo core -> Verify core** now shows a
  green inline result and a confirmation dialog with the version and path; a failed check is
  highlighted in red.
- New English / Chinese strings and dark/light liquid-glass styling for the tree, table and
  switches.

### Verify

- All existing tests plus the new download tests pass: `pytest` (230 tests).
- `ruff check src tests` is clean.
- Listener syntax was checked against the bundled core (Mihomo v1.19.33) and a real core was
  started to confirm `name/type: mixed/listen: 127.0.0.1/port/proxy` binds correctly.

Download `MihomoLite-Setup-0.5.1-x64.exe` or `MihomoLite-0.5.1-portable-x64.zip`.
Windows 10/11 x64; the installer is not code-signed yet.

## 中文

### 本次更新

- **修复：系统/注册表代理环境下连接一直卡在启动。** 本地 controller 客户端没有禁用环境代理，
  httpx 会把发往 `127.0.0.1` 的 API 请求交给 WinINET 代理，导致始终等不到内核就绪。现在
  本地 API 客户端会绕过系统代理，与其它本地传输保持一致。
- **新增“下载”页面。** 普通单线程下载保持原样：填写链接和保存路径，文件经过本地 Mihomo
  mixed 端口下载。
- **多线程下载（可选，默认关闭）。** 先发 HEAD 请求检查文件大小和 `Accept-Ranges`；
  支持分段时按文件大小自动选择 4–16 个线程（也可手动指定），预分配文件后各分段按偏移
  直接写入，无需最后合并；空闲线程会从剩余最长的分段中继续切分。失败分段按指数退避
  重试，最多 5 次。分段进度、ETag 与 Last-Modified 写入状态文件，支持断点续传；若服务器
  校验信息变化则重新下载。
- **多节点并行（可选，默认关闭，依赖多线程下载）。** 可跨订阅、跨配置勾选节点。运行副本
  （而不是导入的原始配置）会为每个选中节点生成一个 `mixed` listener，只绑定
  `127.0.0.1` 的空闲端口；每条 listener 固定走指定节点，不调用 controller 切换节点。
  界面显示各节点实时速度与状态；节点失败会被暂时标记异常，未完成分段转给其他节点；
  若多个出口 IP 收到 HTTP 403/429，会自动降低并发并退回单节点，同时给出提示。
- **默认安全。** 两个开关都关闭时，运行副本与原来完全一致：不生成 listeners、不追加
  节点、不启动下载调度器。已连接时切换开关会通过现有 controller 重新生成并热加载运行
  副本；未连接时会提示重新连接后生效。
- **入口与配置列表更清晰。** 下载页会说明设置里的开关只是启用加速，并提供“打开下载设置”按钮；
  设置页提供“打开下载页面”按钮。配置页改为玻璃卡片，带“当前使用/已选中”标识，多个订阅
  一目了然。最小化到托盘时会弹出提示；如希望最小化后保留在任务栏，可在
  Settings -> Application 关闭“最小化到托盘”。
- **内核校验结果更明显。** **Settings -> Mihomo core -> Verify core** 现在会显示绿色结果，
  并弹出包含版本与路径的确认框；校验失败则以红色提示。
- 新增中英文文案，以及树、表格和开关的深浅色液态玻璃样式。

### 验证

- 原有测试与新增下载测试全部通过：`pytest`（230 个测试）。
- `ruff check src tests` 无报错。
- listeners 写法已对照内置内核（Mihomo v1.19.33）的官方文档与源码，并用真实内核启动验证
  `name/type: mixed/listen: 127.0.0.1/port/proxy` 能正常绑定。

下载 `MihomoLite-Setup-0.5.1-x64.exe` 或 `MihomoLite-0.5.1-portable-x64.zip`。
支持 Windows 10/11 x64，安装包暂未签名。
