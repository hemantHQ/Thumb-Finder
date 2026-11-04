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
