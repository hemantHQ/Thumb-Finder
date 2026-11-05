# Thumb Finder

**Discover. Explore. Get Inspired.**

Thumb Finder is a portable PySide6 desktop application for discovering and saving YouTube video thumbnails. The displayed product version remains **v1.0**; an internal build number allows maintenance updates without changing the displayed version.

## Portable downloads

- **Windows:** download `Thumb-Finder-Windows-Portable.zip`, extract the folder, and run `Thumb-Finder.exe`. No installer or Python installation is required. Keep the extracted folder in a location your Windows account can modify so automatic updates can replace its files.
- **Intel macOS:** open `Thumb-Finder-macOS-Intel.dmg` and copy `Thumb Finder.app` to a user-writable Applications folder (for example `~/Applications`). The portable app bundle contains its runtime; Python is not required. The matching portable ZIP is used by the in-app updater.

The app is currently built for Windows x64 and Intel macOS (x86_64). Apple Silicon native builds are disabled for now.

## Automatic updates

At startup, the app checks the latest public release from `https://github.com/hemantHQ/Thumb-Finder`. If a compatible update is available, choose **Download & update**. The app downloads the correct platform package, verifies its SHA-256 checksum, and asks whether to restart. On confirmation, a separate helper waits for the app to close, replaces the old portable app files, and launches the updated app. If the network is unavailable, the current app continues to start normally.

For reliable automatic replacement, keep the portable app in a folder/bundle location writable by your user account. If the app is inside a protected system folder, update replacement may require manual installation from the GitHub release page.

The update manifest uses an internal build number. The visible version remains **v1.0** until the publisher explicitly changes it.

## API key setup

Users do not enter a YouTube API key. The publisher adds a GitHub Actions repository secret named `YOUTUBE_API_KEY`; release builds inject it into the client application.

**Security warning:** a key embedded in a public desktop application can be extracted. GitHub Secrets protect it during CI, not after distribution. Restrict the key to the YouTube Data API, monitor quota, and rotate it if abused. See `docs/SECURITY.md`.

## Build and release

Push a matching tag such as `v1.0.0`, or manually run the GitHub Actions workflow for that tag. The workflow builds Windows x64 and Intel macOS packages, generates checksums and an update manifest, and publishes them to the GitHub Release.

Required repository secret: `YOUTUBE_API_KEY`.

## Local developer run (Windows)

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:THUMB_FINDER_YOUTUBE_API_KEY = "your-development-key"
python -m thumb_finder.app
```

Never commit a real key.

## Current feature baseline

- Actor Name and Topic Search.
- Similar Thumbnail Image search using local visual comparison against a bounded pool of fetched YouTube thumbnails; not internet-wide reverse-image search.
- Long-form duration filtering, automatic gallery loading, and thumbnail downloads.
- Startup update checks, checksum verification, portable self-update, and diagnostic logging.

Diagnostic logs are written to `~/.thumb_finder/logs/thumb_finder.log`.

The footer displays `Thumb Finder v1.0 - Hemant`.
