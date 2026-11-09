@echo off
setlocal
cd /d "%~dp0"
title Thumb Finder - LaMa Object Removal
 echo ==========================================================
echo Thumb Finder - Optional Big-LaMa Object Removal
echo ==========================================================
echo.
echo The object-removal engine is optional and is NOT included in the app download.
echo First use downloads a separate PyTorch runtime and the Big-LaMa model.
echo The LaMa model itself is a small download; PyTorch is the larger dependency.
echo The model is cached and kept loaded while Thumb Finder is open.
echo CPU processing works; supported NVIDIA GPUs may accelerate processing.
echo All image processing is local; thumbnails are not uploaded.
echo.
echo Run Run_Thumb_Finder_Debug.bat to start Thumb Finder.
pause
