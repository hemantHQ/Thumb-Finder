@echo off
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name "Thumb Finder" --collect-all PySide6 --collect-all cv2 --collect-all numpy --add-data "thumb_finder\app_icon.svg;." thumb_finder\app.py
echo.
echo Build complete. Find the app in the dist folder.
pause
