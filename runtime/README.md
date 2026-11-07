# runtime/

This folder is only used in a portable (zip) layout, where the core binary may sit next to
the executable. The installed application keeps its runtime files under
%LOCALAPPDATA%\MihomoLite\runtime instead:

- generated.yaml - the hardened config the core actually loads (regenerated on every start)
- session.json   - pid/ports of the running core, used to clean up after a crash

Nothing here is committed except this file.
