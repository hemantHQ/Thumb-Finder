# Architecture

- `thumb_finder/version.py` is the displayed application version source.
- `thumb_finder/api_config.py` is generated during release builds from the
  `YOUTUBE_API_KEY`, repository name, and internal GitHub Actions build number.
- `thumb_finder/updater.py` validates portable archives and launches a detached
  PowerShell or shell helper to replace the app after it exits.
- `scripts/create_icons.py` creates the Windows ICO and macOS iconset from the
  Thumb Finder brand mark.
- `scripts/create_update_manifest.py` writes the release manifest with platform
  archive names and SHA-256 checksums.
- GitHub Actions builds Windows x64 and Intel macOS portable packages, a macOS DMG,
  checksums, and the update manifest.
- The update checker runs asynchronously; network failures do not block startup.
- Diagnostic logs are written to `~/.thumb_finder/logs/`.

The app currently embeds its YouTube API key. Public desktop binaries can be
reverse-engineered, so the key should be restricted and monitored.
