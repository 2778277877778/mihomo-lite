# Security policy

## Reporting

Please report vulnerabilities privately via GitHub Security Advisories
("Report a vulnerability" on the repository Security tab). Do not open a public issue for
anything that could be exploited before a fix is available.

You can expect an acknowledgement within a few days. This is a volunteer project, so please
allow reasonable time for a fix before disclosure.

## Threat model

Mihomo Lite is a desktop client that runs a third-party proxy core on the user's machine.
It does not provide isolation from the local user account.

What we defend against:

- **Remote exposure of the proxy/controller.** The core always binds to 127.0.0.1 with a
  fresh random secret per run. Imported YAML cannot change the controller, bind address or
  LAN access: the generator overwrites those fields.
- **Secret leakage into logs.** Secrets are registered with the logging filter and redacted
  from every record, including the in-memory ring buffer shown in the UI.
- **Persistent network breakage after a crash.** The previous system proxy state is
  journaled before any change and restored on the next start when the owner process is gone.
- **Malicious subscription content.** Profiles are parsed with yaml.safe_load, size-limited,
  and validated before use; a failed update keeps the previous working file.

What we do not defend against:

- A malicious local process running as the same user (it could read the config directory).
- The proxy core itself, or the remote servers a profile points at.
- TUN/VPN style traffic capture (not implemented in v0.1).

## Supported versions

Only the latest release receives security fixes.

## Dependencies

- PySide6 / Qt (LGPL-3.0), dynamically linked.
- httpx, websockets, PyYAML, pydantic (permissive licenses).
- Mihomo core (GPL-3.0) is downloaded separately and is out of scope for fixes here; report
  core issues upstream.
