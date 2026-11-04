# Thumb Finder

**Discover. Explore. Get Inspired.**

Thumb Finder is a PySide6 desktop application for discovering and saving YouTube
video thumbnails. Current project milestone: **v0.10.0**.

## API key setup for users

Users do not enter a YouTube API key. The publisher adds a GitHub Actions repository
secret named `YOUTUBE_API_KEY`; tagged release builds inject it into the app.

**Security warning:** the key is embedded in the public EXE/APP and can be extracted.
GitHub Secrets do not make a client-embedded key private. See `docs/SECURITY.md`.

## Build and release

Push a version tag such as `v0.10.0` to trigger `.github/workflows/release.yml`.
GitHub Actions builds Windows and macOS artifacts on native runners and publishes
a GitHub Release.

Required repository secret: `YOUTUBE_API_KEY`.

Protect the default branch and release tags. Review workflow changes carefully:
the release job has access to the API secret.

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
- Similar Thumbnail Image search using local visual comparison against a bounded
  pool of fetched YouTube thumbnails; not internet-wide reverse-image search.
- Long-form duration filtering, auto-loading, and thumbnail downloads.

## Planned work

- Mandatory update client and signed update manifest.
- Windows/macOS code signing and macOS notarization.
- Public beta testing and release hardening.
