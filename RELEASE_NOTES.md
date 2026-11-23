# Mihomo Lite v0.4.3

Logs that keep up, and a fixed release process.

## English

### Fixed

- **Logs page stopped updating** once the in-memory buffer filled up: the view used the
  record count to detect new lines, so once the buffer was full nothing new appeared.
  Records now carry sequence numbers, the buffer holds 5000 entries, and dropped lines are
  announced explicitly. Copy/export follow the same data.

### Added

- A release checklist in `docs/RELEASE.md` and `scripts/bump_version.py`, so every future
  release updates the version, README, bilingual notes and published assets consistently.

### Install

`MihomoLite-Setup-0.4.3-x64.exe` or `MihomoLite-v0.4.3-portable-x64.zip`,
Windows 10/11 x64. The installer is not code-signed yet.

## 中文

### 修复

- **Logs 页显示到一定量后不再更新**：之前用"条数变化"判断新日志，缓冲区满后条数不变，
  新日志永远不显示。现在每条日志带序号，容量提升到 5000 条，被丢弃的行会明确提示，
  复制/导出同样完整。

### 新增

- 新增发布清单 `docs/RELEASE.md` 与 `scripts/bump_version.py`：以后每次发布都统一更新
  版本号、README、中英双语说明与发布资产。

### 安装

`MihomoLite-Setup-0.4.3-x64.exe` 或 `MihomoLite-v0.4.3-portable-x64.zip`，
支持 Windows 10/11 x64，安装包暂未签名。
