# Intel macOS portable app

GitHub Actions builds `Thumb Finder.app` on a native Intel macOS runner. The release
contains both `Thumb-Finder-macOS-Intel.dmg` for drag-and-drop use and
`Thumb-Finder-macOS-Intel-Portable.zip` for the in-app updater.

Copy the app bundle to a user-writable Applications folder (for example
`~/Applications`) to allow automatic updates. Python is not required.

The app is not currently signed or notarized. Gatekeeper warnings may appear.
