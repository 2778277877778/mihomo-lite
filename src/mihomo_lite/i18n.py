"""Tiny two-language layer (English source strings, Chinese translations).

Widgets are built in English and translated by walking the tree once, so pages
never have to be rewritten for every label. Dynamic strings call tr() directly.
"""

from __future__ import annotations

LANGUAGES = {"en": "English", "zh": "中文"}

_current = "en"

ZH: dict[str, str] = {
    # window / navigation
    "Dashboard": "仪表盘",
    "Proxies": "代理",
    "Profiles": "配置",
    "Settings": "设置",
    "Logs": "日志",
    "Traffic": "流量",
    "Live speed, session totals and today's usage.": "实时速度、本次会话与今日用量。",
    "Last 2 minutes": "最近 2 分钟",
    "Session": "本次会话",
    "Today": "今日",
    "Reset today": "重置今日",
    "Today download / upload": "今日下载 / 上传",
    "Peak speed (session)": "峰值速度（本次会话）",
    "Ready": "就绪",
    "Disconnected": "未连接",
    "Connecting…": "正在连接…",
    "Connected": "已连接",
    "Disconnecting…": "正在断开…",
    "Error": "错误",
    # dashboard
    "Start, stop and watch your traffic.": "启动、停止并查看流量。",
    "Traffic is going straight to the internet.": "流量直接走本地网络。",
    "Validating the profile and starting the core.": "正在校验配置并启动内核。",
    "Your system proxy points at the local Mihomo instance.": "系统代理已指向本地 Mihomo 实例。",
    "Restoring the previous system proxy.": "正在恢复之前的系统代理。",
    "Something went wrong": "出了点问题",
    "Open the Logs page for the exact reason.": "打开日志页查看具体原因。",
    "Connect": "连接",
    "Disconnect": "断开",
    "DOWNLOAD": "下载",
    "UPLOAD": "上传",
    "SESSION DOWNLOAD": "本次下载",
    "SESSION UPLOAD": "本次上传",
    "Profile": "配置",
    "Mihomo core": "Mihomo 内核",
    "Local endpoints": "本地端口",
    "System proxy": "系统代理",
    "Core output": "内核输出",
    "none selected": "未选择",
    "not running": "未运行",
    "will be enabled": "将启用",
    "disabled": "已禁用",
    "TUN mode (administrator required)": "TUN 模式（需要管理员）",
    # proxies
    "Pick a group, then a node.": "先选策略组，再选节点。",
    "Refresh": "刷新",
    "Test latency": "测延迟",
    "Select a policy group.": "请选择策略组。",
    "Use selected node": "使用所选节点",
    "Connect first to load proxy groups.": "先连接才能加载代理组。",
    "Connect to load nodes": "连接后加载节点",
    "Import a profile first, then connect.": "请先导入配置，再连接。",
    "Filter nodes…": "过滤节点…",
    "Check IP": "检测 IP",
    "Test all delays": "全部测延迟",
    "Outbound mode": "出站模式",
    "Current node": "当前节点",
    "Latency": "延迟",
    "Usage": "用量",
    "Session usage": "本次用量",
    "IP address": "IP 地址",
    "Latency fluctuation (current node)": "延迟波动（当前节点）",
    "Waiting for latency samples…": "等待延迟采样…",
    "Checking…": "检测中…",
    "LAN IP": "内网 IP",
    "Speed test": "测速",
    "Connect first.": "请先连接。",
    "Connect first and pick a node.": "请先连接并选择节点。",
    "Speed test needs a Selector group.": "测速需要 Selector 策略组。",
    "Checking the public IP…": "正在检测公网 IP…",
    "Connected first?": "先连接",
    # profiles
    "Imports stay untouched; a generated copy runs.": "导入的文件不会被改动，运行时使用生成的副本。",
    "Update all": "全部更新",
    "Import YAML…": "导入 YAML…",
    "Import QR…": "导入二维码…",
    "Add subscription…": "添加订阅…",
    "Update subscription": "更新订阅",
    "Delete": "删除",
    "Use this profile": "使用此配置",
    "No profile selected.": "未选择配置。",
    "Updating…": "正在更新…",
    "Updating subscriptions…": "正在更新订阅…",
    "Local file": "本地文件",
    "Subscription": "订阅",
    "Rule check": "规则检查",
    # settings
    "Changes are saved locally in your user profile.": "设置保存在你的用户目录中。",
    "Download core (≈22 MB)": "下载内核（约 22 MB）",
    "Verify core": "校验内核",
    "Remove downloaded core": "移除已下载内核",
    "Force stop core": "强制结束内核",
    "Browse…": "浏览…",
    "Network": "网络",
    "Only localhost is exposed. Ports set to 0 pick a free high port on every start.": "只监听本机。端口填 0 表示每次自动选择空闲高端口。",
    "Use the Windows system proxy while connected": "连接时使用 Windows 系统代理",
    "TUN mode (captures all traffic, needs administrator)": "TUN 模式（接管全部流量，需要管理员）",
    "TUN stack": "TUN 栈",
    "A verified Mihomo core ships with the app. You can point it at another mihomo.exe, or download a newer official Windows build.": "安装包已内置经过校验的 Mihomo 内核；也可以指定其它 mihomo.exe，或下载更新的官方 Windows 版本。",
    "Automatic": "自动",
    "Automatic (app data or next to the executable)": "自动（应用数据目录或程序目录）",
    "Mixed": "混合",
    "System": "系统",
    "wintun.dll not installed (required for TUN)": "wintun.dll 未安装（TUN 需要）",
    "wintun.dll: core not ready": "wintun.dll：内核未就绪",
    "Hijack DNS in TUN mode (recommended)": "TUN 模式下劫持 DNS（推荐）",
    "Download wintun": "下载 wintun",
    "Mixed port": "混合端口",
    "API port": "API 端口",
    "Bypass list": "绕过列表",
    "Application": "应用",
    "Startup, tray and appearance.": "启动、托盘与外观。",
    "Start with Windows": "开机自启",
    "Close to the tray instead of quitting": "关闭窗口时最小化到托盘",
    "Minimise to the tray": "最小化到托盘",
    "Theme": "主题",
    "Dark": "深色",
    "Light": "浅色",
    "Log level": "日志级别",
    "Update subscriptions automatically": "自动更新订阅",
    "Update interval": "更新间隔",
    "Connect on launch": "启动时自动连接",
    "Invert scroll direction": "反转滚动方向",
    "Language": "语言",
    "Save settings": "保存设置",
    "Open data folder": "打开数据目录",
    # logs
    "App and core output; secrets are redacted.": "应用与内核输出，密钥已脱敏。",
    "Copy": "复制",
    "Export…": "导出…",
    "Clear view": "清空",
    "Open log folder": "打开日志目录",
    # tray
    "Show window": "显示窗口",
    "Quit": "退出",
    # dynamic
    "Mihomo Lite is still running": "Mihomo Lite 仍在运行",
    "The proxy keeps working. Use the tray icon to reopen or quit.": "代理继续工作，可用托盘图标重新打开或退出。",
    "Mihomo Lite": "Mihomo Lite",
    "Connection error - see Logs for details.": "连接出错，详见日志。",
    "Connected - traffic is going through Mihomo.": "已连接，流量经由 Mihomo。",
    "Disconnected.": "已断开。",
    "TUN mode": "TUN 模式",
    "Administrator required": "需要管理员权限",
    "The app will restart and connect again automatically.": "程序将重启并自动重新连接。",
    "Restart failed": "重启失败",
    "Mihomo Lite could not restart as administrator. Start it manually with 'Run as administrator', or turn off TUN mode.": "无法以管理员身份重启。请手动右键“以管理员身份运行”，或关闭 TUN 模式。",
    "Connected. Traffic is now going through Mihomo.": "已连接，流量开始经由 Mihomo。",
    "The connection failed. Open the app for details.": "连接失败，打开程序查看详情。",
    "Running in the background. Use the tray icon to open.": "已在后台运行，点击托盘图标打开。",
    "system proxy": "系统代理",
    "off": "关闭",
    "running": "运行中",
}


def set_language(language: str) -> None:
    global _current
    _current = language if language in LANGUAGES else "en"


def get_language() -> str:
    return _current


def tr(text: str) -> str:
    if _current == "zh":
        return ZH.get(text, text)
    return text


def translate_widget_tree(root) -> None:
    """Translate the static texts of an already-built widget tree."""
    if _current == "en" or root is None:
        return
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QGroupBox,
        QLabel,
        QListWidget,
        QPushButton,
        QRadioButton,
    )

    for widget in root.findChildren(QLabel):
        text = widget.text()
        if text in ZH:
            widget.setText(ZH[text])
    for cls in (QPushButton, QCheckBox, QRadioButton):
        for widget in root.findChildren(cls):
            text = widget.text()
            if text in ZH:
                widget.setText(ZH[text])
    for box in root.findChildren(QGroupBox):
        if box.title() in ZH:
            box.setTitle(ZH[box.title()])
    for combo in root.findChildren(QComboBox):
        for index in range(combo.count()):
            text = combo.itemText(index)
            if text in ZH:
                combo.setItemText(index, ZH[text])
    for listing in root.findChildren(QListWidget):
        for row in range(listing.count()):
            item = listing.item(row)
            if item.text() in ZH:
                item.setText(ZH[item.text()])
