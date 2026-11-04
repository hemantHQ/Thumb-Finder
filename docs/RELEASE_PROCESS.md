# Release process

1. Update `thumb_finder/version.py` and `pyproject.toml` to the same semantic version.
2. Update the changelog and commit the changes.
3. Push the changes to the default branch.
4. Create and push a matching tag, for example:
   `git tag v1.0.0` then `git push origin v1.0.0`.
5. GitHub Actions validates the tag and builds:
   - Windows: `Thumb-Finder-Setup.exe` using Inno Setup.
   - macOS: `Thumb-Finder-macOS-Apple-Silicon.dmg and Thumb-Finder-macOS-Intel.dmg` containing the `.app`.
6. The workflow publishes both installers and `SHA256SUMS.txt` to the matching GitHub Release.

## Re-run a build for an existing tag

If the tag/release already exists and the workflow did not run:

1. Open the repository's **Actions** tab.
2. Select **Build and publish Thumb Finder**.
3. Click **Run workflow**.
4. Enter the existing tag, for example `v1.0.0`.
5. Click **Run workflow**.

The manual run checks out that tag, verifies its version, builds both installers,
and uploads/replaces the assets on the existing release.

## Required repository configuration

Add a GitHub Actions repository secret named `YOUTUBE_API_KEY`.
Do not commit the real key or paste it into public issues or chat.

Protect the default branch and release tags. Only trusted maintainers should
trigger secret-bearing release builds.

## Important release limitations

- The workflow is prepared but still needs a real run on GitHub Actions.
- Windows EXE is an installer, not a single portable executable.
- macOS DMG is not currently code-signed or notarized; Gatekeeper warnings may appear.
- Mandatory in-app update checks are not implemented yet.
- The API key is embedded in the distributed app and can be extracted.
