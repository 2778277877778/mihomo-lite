# Architecture

## Goals

1. The GUI must never block on network or process work.
2. Exactly one component owns the connection state.
3. A crash must not leave the user's Windows proxy pointing at a dead core.
4. The user's original profile must never be modified.

## Layers

| Layer | Package | Responsibility |
| --- | --- | --- |
| Presentation | mihomo_lite.ui | Widgets, pages, tray, theme. Observes state, calls core services. |

The window is frameless and painted by ui/glass.py: a rounded shell clips an aurora
backdrop, and the top-level window asks Windows for an acrylic blur so translucent surfaces
read as frosted glass over the desktop. Window dragging and edge resizing are handled
through WM_NCHITTEST, so native snap layouts keep working.
| Application | mihomo_lite.core | ConnectionManager, ProfileManager, ProxyManager, TrafficMonitor, SettingsStore. |
| Infrastructure | mihomo_lite.mihomo, mihomo_lite.system, mihomo_lite.config | QProcess wrapper, REST client, WebSocket, Windows proxy, YAML load/validate/generate. |
| Models | mihomo_lite.models | Pydantic settings, profile metadata, proxy groups, connection state enum. |
| External | Mihomo core | Separate process, controlled over a localhost REST API. |

Dependency direction is one-way: ui -> core -> infrastructure -> models/utils.
No infrastructure module imports a widget, and no page touches QProcess or httpx directly.

## Connection state machine

ConnectionState: stopped -> starting -> connected -> stopping -> stopped, with error reachable
from starting/connected.

ConnectionManager is the only writer. It emits state_changed, session_changed, error_changed
and warning; the dashboard, tray, status bar and pages all follow those signals.

### Connect

~~~text
validate active profile
  -> pick free ports (never the well-known 7890/7897/9090 range)
  -> generate hardened runtime config with a fresh secret
  -> locate/verify core binary
  -> QProcess.start(-d <runtime> -f <runtime>/generated.yaml)
  -> worker thread polls GET /version until ready (20 s budget)
  -> apply system proxy (journal first)
  -> start traffic WebSocket
  -> state = connected
~~~

Any failure at the earlier stages stops the core, restores the proxy if it was changed and
moves to error with a human-readable message.

### Disconnect (order matters)

~~~text
state = stopping
  -> stop traffic socket
  -> restore the journalled system proxy
  -> close the API client
  -> terminate the core, kill after 1.2 s
  -> state = stopped
~~~

The proxy is restored first so the user is never left pointing at a listener that is
already gone.

## Configuration pipeline

~~~text
profiles/<id>/original.yaml   immutable, exactly what the user imported
        |
        v  validate (pydantic-free, explicit rules)
runtime/generated.yaml        hardened copy written atomically
~~~

Rule checking (config/rules.py) runs before the copy is written. It validates rule
types, referenced policies and rule-providers, duplicate rules, dead rules after MATCH,
stray whitespace and missing no-resolve hints. A profile whose rules do not parse is
rejected at import; warnings are shown on the Profiles page. When a profile has no final
MATCH rule, the generator appends one (first selector group, else DIRECT) so unmatched
traffic no longer depends on the core default.

Hardening in config/generator.py:

- external-controller is forced to 127.0.0.1:<random port>
- secret is a fresh 32-byte URL-safe token every start
- allow-lan false, bind-address 127.0.0.1
- tun.enable false (v0.1 has no TUN)
- port / socks-port / redir-port / tproxy-port all 0
- listeners removed
- DNS listen forced to localhost when it is not already
- profile.store-selected true

This means a hostile or careless subscription cannot expose the proxy to the LAN or open a
remote control port.

## TUN mode

TUN is opt-in (Settings -> Network). Because a virtual adapter needs administrator rights,
the connection manager checks elevation first and emits `elevation_required`; the window
offers to relaunch the app elevated and reconnect. The generator then emits a TUN section
(auto-route, auto-detect-interface, optional DNS hijack) plus a fake-ip DNS block, and the
system proxy is deliberately left untouched. The core uses `wintun.dll`, which is not
bundled: Settings downloads the official build on request and stores it next to the core.

## Subscription updates

core/update_scheduler.py ticks every 15 minutes (first check after 2 minutes) and refreshes
subscriptions that are older than the configured interval (1-48 h). Updates run one at a
time through TaskRunner, keep the previous file as previous.yaml, validate the new content
before replacing it, and never interrupt a running connection. The active profile is
announced after an update so the UI can ask for a reconnect.

## System proxy safety

system/proxy.py uses the WinINET per-connection option API (INTERNET_OPTION_PER_CONNECTION_OPTION)
and mirrors the result into HKCU\...\Internet Settings. Two details matter:

- ctypes functions must declare argtypes/restype, otherwise 64-bit pointer truncation makes
  the calls fail silently.
- Before the first write, a journal is written:

~~~json
{"pid": 1234, "created_at": 1700000000.0, "snapshot": {"flags": 3, "server": "...", "bypass": "..."}}
~~~

On startup ConnectionManager.recover_after_crash() replays the journal when the recorded PID
is no longer alive, reaping an orphaned core process first. The journal is deleted only after
a successful restore, so a crash during restore is retried next start.

## Threading model

- Main thread: all Qt widgets, QProcess signals, state machine transitions.
- QThreadPool: REST calls (httpx) and subscription downloads.
- Dedicated QThread: traffic WebSocket, running its own asyncio loop with exponential
  backoff. Signals cross back to the main thread through Qt's queued connections.

No qasync, no asyncio integration into the Qt loop. This keeps the dependency surface tiny
and the failure modes obvious.

## Security notes

- The core API binds to 127.0.0.1 only, with a per-run secret. Secrets are registered with
  the logging filter and replaced by *** in every record.
- Imported YAML cannot change the controller, bind address or open LAN access.
- The app never runs the core with elevated privileges; TUN is out of scope precisely
  because it would require them.
- The core binary is bundled unmodified at build time (pinned upstream release, GPL-3.0).
  A newer core can still be downloaded on explicit user action; the downloaded copy wins
  over the bundled one and can be removed again from Settings.

## Extending

- New page: add a widget under ui/, take Services, connect to existing signals.
- New core capability: add a method to mihomo/api.py, then expose it through a manager.
- Subscription providers that need parsing: extend core/profile_manager.py, keep the
  backup-then-replace invariant.
- TUN: implement as a separate module behind a capability check, never in the V0.1 path.
