# User guide

## 1. Install

Run the installer, then launch **Mihomo Lite** from the Start Menu. The app starts without a
core: it does not ship one.

## 2. The core is included

The installer ships a Mihomo core, so there is nothing to download before the first run.
**Settings -> Mihomo core** shows the version and where the binary came from
(bundled, downloaded, or a custom path).

Optional actions:

- **Download core** fetches a newer official Windows build into
  %LOCALAPPDATA%\MihomoLite\core and uses it from then on.
- **Remove downloaded core** goes back to the bundled binary.
- **Browse...** points the app at your own mihomo.exe.
- **Verify core** runs the binary once to confirm it works.

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
