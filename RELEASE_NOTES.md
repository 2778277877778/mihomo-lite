# Mihomo Lite v0.2.1

Six reliability fixes for TUN mode, uninstall and subscription updates.

## English

### Fixes

- **Elevated restart no longer races the single-instance lock** - the new process retries
  for up to 2.5 s, and the old one releases the lock before exiting, so TUN restarts open
  the window instead of quitting silently.
- **Uninstalling restores the system proxy** - the uninstaller asks the running app to quit
  gracefully (`--shutdown`) and repairs any leftover journal before falling back to taskkill.
- **TUN failures are visible** - after connecting, core output is checked for TUN/wintun
  errors; a broken tunnel now produces a warning instead of a green light.
- **Subscription tokens are redacted** - URLs in download errors and the profile details
  mask token/key/auth parameters.
- **Updated active profiles reload live** - when the active subscription is refreshed while
  connected, the runtime config is rewritten and pushed to the core via PUT /configs.
- **Connect switch reflects reality** - declining the UAC prompt resets the switch instead
  of leaving it on.

### Install

`MihomoLite-Setup-0.2.1-x64.exe` or `MihomoLite-v0.2.1-portable-x64.zip`.
Windows 10/11 x64. The installer is not code-signed yet.

## 中文

### 修复

- **提权重启不再与单实例锁冲突**：新进程最多重试 2.5 秒，旧进程退出前主动释放锁，
  TUN 重启不会再静默退出。
- **卸载会恢复系统代理**：卸载器先用 `--shutdown` 让运行中的程序优雅退出，并兜底修复
  残留的代理 journal，最后才使用 taskkill。
- **TUN 失败可见**：连接后检查内核输出中的 TUN/wintun 错误，隧道没起来会给出警告，
  不再显示"已连接"的绿灯。
- **订阅 token 脱敏**：下载错误信息和个人资料详情中的 URL 会隐藏 token/key/auth 参数。
- **活动配置热重载**：连接期间活动订阅更新后，自动重写运行配置并通过 PUT /configs
  让内核立即生效。
- **连接开关与实际状态一致**：取消 UAC 授权后开关会复位，不会停在"开"。

### 安装

`MihomoLite-Setup-0.2.1-x64.exe` 或 `MihomoLite-v0.2.1-portable-x64.zip`。
支持 Windows 10/11 x64，安装包暂未签名。
