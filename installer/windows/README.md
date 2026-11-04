# Windows installer

GitHub Actions builds the PyInstaller application folder, then uses Inno Setup
to create `Thumb-Finder-Setup.exe`.

For a local build, first build `dist/Thumb-Finder` with PyInstaller, install
Inno Setup 6, then run:

```powershell
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.0 installer/windows/thumb_finder.iss
```

The installer is written to `installer/windows/output/`.
