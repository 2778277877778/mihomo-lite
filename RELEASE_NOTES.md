# Mihomo Lite v0.4.2

Adaptive ports so a busy port no longer breaks startup.

## English

- If the core exits during startup (a port was taken between selection and bind), the
  client retries automatically up to 3 times with fresh random ports.
- DNS `listen` is moved to a free localhost port instead of a fixed, often busy one.
- Every retry is logged, so the Logs page shows exactly what happened.

Download `MihomoLite-Setup-0.4.2-x64.exe` or `MihomoLite-v0.4.2-portable-x64.zip`.
Windows 10/11 x64; the installer is not code-signed yet.

## 中文

- 端口自适应：内核启动阶段因端口被占用而退出时，自动换一组随机端口重试，最多 3 次。
- DNS `listen` 改为自动选择空闲本地端口，不再固定使用可能被占用的端口。
- 每次重试都会写入日志，Logs 页可直接看到原因。

下载 `MihomoLite-Setup-0.4.2-x64.exe` 或 `MihomoLite-v0.4.2-portable-x64.zip`。
支持 Windows 10/11 x64，安装包暂未签名。
