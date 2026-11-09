# Local debugging (no build)

## One-time setup

Open Command Prompt in this folder and run:

```bat
py -m pip install -r requirements.txt
```

Use the Python launcher default interpreter. If `py` is unavailable, use `python -m pip install -r requirements.txt`. The selected Python version must have compatible PySide6, OpenCV and NumPy wheels.

## Launch

Double-click `Run_Thumb_Finder_Debug.bat`, or run:

```bat
py run_app.py
```

The launcher performs no installation and no compilation. It starts immediately with the already-installed dependencies. If a dependency is missing, the launcher prints the exact pip command to run once.

## API key

The first launch asks for a YouTube Data API key after the main window appears. It is stored in `%USERPROFILE%\.thumb_finder\config.json`. Do not share this file.

## Error reporting

Logs are written to `%USERPROFILE%\.thumb_finder\logs\thumb_finder.log` with rotation. Search, preview and download workers log full tracebacks; the UI displays concise errors.
