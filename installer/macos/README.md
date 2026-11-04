# macOS installer

GitHub Actions builds `dist/Thumb Finder.app` on a native macOS runner and
packages it as `Thumb-Finder-macOS.dmg` using `hdiutil`.

The current workflow does not sign or notarize the app. For public distribution,
configure an Apple Developer ID certificate and notarization credentials in
GitHub Actions before announcing the release. Without notarization, macOS may
show Gatekeeper warnings.
