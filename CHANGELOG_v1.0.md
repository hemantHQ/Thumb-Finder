# Thumb Finder v1.0

## Release foundation
- Standalone Windows installer and macOS application bundle/DMG workflow.
- Bundled Python runtime and application dependencies for end users.
- Startup loading screen and GitHub release update check.
- Update-available dialog with a link to the published release.
- Startup and unexpected-error handling with diagnostic logging.
- Footer branding: `Thumb Finder v1.0 - Hemant`.

## Search and downloads
- Actor Name and Topic Search.
- Similar Thumbnail Image search using local visual comparison against a bounded
  pool of fetched YouTube thumbnails.
- Long-form duration filtering, auto-loading, and thumbnail downloads.

## Build pipeline update (still v1.0)
- Build a native macOS Intel (x86_64) installer alongside the Windows installer.
- Verify the macOS Intel runner architecture before packaging.
- Apple Silicon (ARM64) build is currently disabled; it can be re-enabled later.
- Publish the Intel DMG and include it with the Windows installer in SHA-256 checksums.
### Startup hotfix (v1.0)
- Fixed startup crash caused by the GitHub repository setting not being initialized before the update check.


## Maintenance build improvements (displayed version remains v1.0)

- Added branded Windows ICO and macOS ICNS application icons.
- Added portable Windows ZIP and Intel macOS app/DMG packages.
- Reduced packaging scope by excluding unused optional Qt and scientific modules.
- Added startup release checks against hemantHQ/Thumb-Finder.
- Added platform-aware update downloads, SHA-256 verification, restart confirmation, and helper-based app replacement.
- Improved diagnostic logging and update failure handling.
- Added internal build revisions so updates can be delivered without changing the visible v1.0 version.
