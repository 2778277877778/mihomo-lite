# User guide

## 1. Install

Run the installer, then launch **Mihomo Lite** from the Start Menu. The app starts without a
core: it does not ship one.

## 2. Get a core

Open **Settings -> Mihomo core**:

- Press **Download core** to fetch the official Windows build (about 22 MB). This is a
  one-time download, stored in %LOCALAPPDATA%\MihomoLite\core.
- Or press **Browse...** and choose an existing mihomo.exe.

Press **Verify core** if you want confirmation that the binary runs.

## 3. Import a profile

Open **Profiles**:

- **Import YAML...** for a local file (.yaml or .yml).
- **Add subscription...** for a URL. The app downloads it directly, not through the proxy.

The imported file is stored untouched. A separate runtime copy is generated for the core, so
your original file never changes. The first imported profile becomes active automatically.

## 4. Connect

Press **Connect** on the Dashboard (or the big switch). The sequence is:

1. the profile is validated and a runtime config is written;
2. the core starts on random free ports;
3. your Windows system proxy is pointed at the local mixed port;
4. the status turns green and traffic counters start.

Press again to disconnect. Your previous system proxy setting is restored before the core
stops.

## 5. Switch nodes

Open **Proxies** while connected. Pick a policy group on the left, then either double-click a
node or use **Use selected node**. **Test latency** runs a delay test for the group.

## 6. Tray and autostart

- Closing the window keeps the app in the tray by default; the proxy keeps working.
- Right-click the tray icon for connect/disconnect/quit.
- **Settings -> Application** turns on start-with-Windows, close-to-tray and minimise-to-tray.

## Troubleshooting

**The status stays on "Connecting..."**
Open Logs. A common cause is another client holding the port; the app normally picks a free
one automatically. The core's own output is shown in the same view.

**My internet broke after a crash**
Restart the app: it detects the leftover proxy journal and restores your previous setting.
If you uninstalled while connected, set the proxy manually: Settings -> Network & Internet ->
Proxy, and turn "Use a proxy server" off.

**Another client was running when I connected**
Mihomo Lite takes over the Windows system proxy. Your previous value is saved and restored on
disconnect. Do not run two clients that both manage the system proxy at the same time.

**Where are my files?**
Settings -> **Open data folder**. Everything (profiles, generated config, logs, core) is under
one directory, so uninstalling is a folder removal.

## Uninstall

Disconnect first, then uninstall from Windows Settings. The data folder is not removed
automatically; delete %LOCALAPPDATA%\MihomoLite if you want a clean slate.
