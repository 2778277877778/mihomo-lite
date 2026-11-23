# Contributing

Thanks for helping. This project values small, reviewable changes over big rewrites.

## Before you start

- Open an issue for anything larger than a bug fix, so the design can be agreed first.
- v0.1 deliberately excludes TUN, rule editing and multi-core support. Please do not add
  them without an accepted design issue.

## Workflow

1. Fork, then create a branch: feature/short-name or fix/short-name.
2. Make the change, keeping the layering intact:
   - ui/ may import core/, models/, utils/;
   - core/ may import mihomo/, system/, config/, models/;
   - nothing imports ui/ except app.py and main_window.py.
3. Add or update tests. Bug fixes should come with a test that fails before the fix.
4. Run:

   ~~~powershell
   $env:QT_QPA_PLATFORM = "offscreen"
   pytest
   ruff check src tests
   ~~~

5. Open the pull request and describe the user-visible behaviour change.

## Rules that are not negotiable

- Never apply the real system proxy in an automated test; use the fake backend.
- Never log a secret or an API token.
- Never let an imported profile change external-controller, bind-address or allow-lan.
- Never ship the Mihomo binary in the repository or the installer.
- Keep the UI usable while work is in flight: anything slow goes through TaskRunner or a
  dedicated thread.

## Releases

Every user-visible change ships as a release: version bump, README update, bilingual
`RELEASE_NOTES.md`, tag, and a verified GitHub release with assets. The full checklist and
the version bump helper are in [docs/RELEASE.md](docs/RELEASE.md) and
`scripts/bump_version.py`.

## Commit messages

Short imperative subject, then a body explaining why when it is not obvious.

~~~text
Restore the system proxy before stopping the core

A crash during shutdown could leave the proxy pointing at a dead port.
~~~

## Code review checklist

- [ ] Layering respected
- [ ] Tests cover the new path
- [ ] No new dependency without justification
- [ ] User-facing strings are short and clear
- [ ] Windows-only code is guarded for non-Windows development
