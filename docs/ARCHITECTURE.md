# Architecture

- `thumb_finder/version.py` is the application version source.
- `thumb_finder/api_config.py` is generated during release builds from the
  `YOUTUBE_API_KEY` GitHub Actions secret; a local environment variable can
  also provide the key.
- GitHub Actions validates the release tag against the app version.
- Native Windows and macOS runners build their respective installers.
- GitHub Releases distributes a Windows Inno Setup `.exe`, a macOS `.dmg`,
  and SHA-256 checksums.

Mandatory update checks, a signed update manifest, code signing, Apple
notarization, and rollback are not yet implemented.
