# Release process

The displayed product version is currently `1.0.0` (footer: `v1.0`). A separate
GitHub Actions build number identifies maintenance builds, so fixes can be delivered
without changing the displayed version.

1. Keep `thumb_finder/version.py` and `pyproject.toml` on the same semantic version.
2. Update the changelog and commit the changes to the default branch.
3. For a new product version, create and push a matching tag (for example `v1.0.0`).
   For a maintenance rebuild of the current version, use **Actions → Build and publish
   Thumb Finder → Run workflow** and enter the existing tag `v1.0.0`.
4. GitHub Actions creates branded portable packages:
   - Windows x64: `Thumb-Finder-Windows-Portable.zip`
   - Intel macOS: `Thumb-Finder-macOS-Intel-Portable.zip`
   - Intel macOS drag-and-drop package: `Thumb-Finder-macOS-Intel.dmg`
5. The workflow generates `SHA256SUMS.txt` and `thumb-finder-update.json`, then
   publishes or replaces the assets on the selected GitHub Release.

## In-app update flow

The app checks the latest public release from `hemantHQ/Thumb-Finder` at startup.
The update manifest selects the correct OS package and carries the internal build
number and SHA-256 checksums. The client downloads the matching archive, verifies its
checksum and archive paths, then asks the user whether to restart. A detached native
helper waits for the app process to exit, swaps the portable app folder/bundle, and
launches the updated app. The app must be located in a folder writable by the current
user for automatic replacement to work.

## Required repository configuration

Add a GitHub Actions repository secret named `YOUTUBE_API_KEY`. Do not commit the
real key. Protect the default branch and release tags; only trusted maintainers
should trigger secret-bearing release builds.

## Distribution limitations

- The builds are portable, but not code-signed/notarized. Windows SmartScreen and
  macOS Gatekeeper warnings may appear.
- Native macOS build is Intel x86_64 only; Apple Silicon native build is disabled.
- The YouTube API key is embedded in the public client and can be extracted. GitHub
  Secrets protect it during CI, not after distribution.
