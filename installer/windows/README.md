# Windows portable package

The release workflow builds `dist/Thumb-Finder` with PyInstaller `--onedir`, then
packages the complete folder as `Thumb-Finder-Windows-Portable.zip`.

Extract the ZIP and run `Thumb-Finder.exe`. Keep the whole folder together and place
it somewhere writable by the current Windows user so the in-app updater can replace
it. Python is not required on the user's PC.

The previous Inno Setup script is retained for reference only; it is no longer used
by the release workflow.
