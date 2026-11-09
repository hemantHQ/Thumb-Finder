# Optional AI image enhancement

Thumb Finder can optionally use Real-ESRGAN x4 for local image enhancement. The main app does not include PyTorch or the model weights. On first use, the editor asks permission, creates an isolated environment under `%LOCALAPPDATA%\\ThumbFinder`, and downloads prebuilt Python packages and the RealESRGAN_x4plus model. If compatible prebuilt wheels are unavailable for the installed Python version, enhancement stops with an error and the rest of Thumb Finder remains usable.

The enhanced result is center-cropped proportionally to 16:9 and resized to exactly 1920x1080. This may crop some content at the edges; it does not stretch the image. The source file remains unchanged until the user saves an edited copy.

Big-LaMa object removal remains a separate optional download. No image is uploaded by either local feature.

## Latest quality fixes
- Text/object selection now retains multiple disconnected mask components, important for words made of separate letters and punctuation.
- The segmentation mask receives a small edge expansion to reduce antialiased text fringes.
- Fixed Enhance runtime bootstrap: it passes the actual runtime directory to the Python compatibility helper instead of referencing an undefined `base` variable.
- AI enhancement preserves the full source composition. Non-16:9 images are fitted into a 1920x1080 canvas rather than being center-cropped.
