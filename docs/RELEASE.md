# Release checklist

Every shipped change follows the same five steps. Do not tag a release without
finishing all of them.

1. **Version number**
   - Bump in three places (the script does all three):
     `src/mihomo_lite/__init__.py`, `pyproject.toml`, `packaging/installer.iss`.
   - Use `0.x.y`: `x` for feature milestones, `y` for fixes and polish.

   ```powershell
   python scripts/bump_version.py 0.4.3
   ```

2. **README details**
   - Add or update the feature bullets that this change affects (English and 中文).
   - Update the test count shown in both "Build from source" sections.
   - If the UI changed, refresh the screenshots in `docs/images`.

3. **Release notes**
   - Rewrite `RELEASE_NOTES.md` for the new version: English section first, then 中文,
     with "what changed", install steps and any security/known-limitation notes.
   - CI publishes this file as the release description.

4. **Commit and tag**

   ```powershell
   git add -A
   git commit -m "Release vX.Y.Z: <one-line summary>"
   git push origin master
   git tag -a vX.Y.Z -m "Mihomo Lite vX.Y.Z"
   git push origin vX.Y.Z
   ```

5. **Verify the published release**
   - Wait for the `tests` and `build` workflows to pass.
   - Open the release page: title is `Mihomo Lite vX.Y.Z`, the description is the new
     bilingual notes, and the three assets exist (setup exe, portable zip, SHA256SUMS).
   - Rebuild the local `dist` and portable zip so local testing matches the release.

## Quick checks before tagging

- `ruff check src tests`
- `pytest`
- `python -m mihomo_lite --selftest` (frozen build) exits 0
- No secrets or local paths added to docs/screenshots

## Automation

`scripts/bump_version.py` only edits the three version strings; the rest is
intentional manual work so the notes actually describe what shipped.
