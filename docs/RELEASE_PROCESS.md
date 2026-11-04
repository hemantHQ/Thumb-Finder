# Release process

1. Update `thumb_finder/version.py` to the new semantic version (for example `0.11.0`).
2. Update `pyproject.toml` to the same version and add release notes.
3. Commit and push the changes to the default branch.
4. Create and push a matching tag, for example `git tag v0.11.0` then `git push origin v0.11.0`.
5. GitHub Actions verifies the tag matches `thumb_finder/version.py`.
6. Native GitHub runners build:
   - Windows: `Thumb-Finder-Setup.exe` (Inno Setup installer)
   - macOS: `Thumb-Finder-macOS.dmg` (disk image containing the `.app`)
7. GitHub Actions publishes both installers and `SHA256SUMS.txt` to one GitHub Release.
8. Test both installers on clean machines before announcing the release.

## Required repository configuration

Add a GitHub Actions repository secret named `YOUTUBE_API_KEY`. Do not commit
the real key or paste it into public issues or chat.

Protect the default branch and release tags. Only trusted maintainers should
trigger secret-bearing release builds.

## Important release limitations

- The workflow has been prepared but must be run on GitHub Actions before it
  can be considered validated.
- Windows EXE is an installer, not a single portable executable.
- macOS DMG is not currently code-signed or notarized. Gatekeeper warnings may
  appear until Apple Developer ID signing and notarization are configured.
- The update prompt/client is a separate implementation task; publishing a new
  version alone does not yet make installed copies check for updates.
- The API key is embedded in the distributed app and can be extracted.
