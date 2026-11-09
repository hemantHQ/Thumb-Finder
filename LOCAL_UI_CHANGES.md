# Thumb Finder — Local UI adjustments

- Theme toggle is a fixed 44×44 icon-only button, so it does not resize when switching between light and dark.
- Removed the configurable movie-duration dropdown. The minimum duration is fixed at 40 minutes.
- Genre dropdown is visible only for Actor Name and Normal Search modes.
- Similar Thumbnail Image mode hides the genre dropdown and compares visual thumbnail features.
- Thumbnail source preference is maxres, then standard, high, medium and default; downloaded source bytes are preserved without upscaling or recompression.
- This is a local-debug source package. Run `Run_Thumb_Finder_Debug.bat`; do not build an EXE.

## Image genre limitation
The current local OpenCV matcher compares visual appearance (color histogram and perceptual hash). It does not semantically classify a thumbnail as Action, Horror, Drama, etc. Reliable automatic genre recognition requires an image-classification model. This package deliberately does not add a large model or network download because the current priority is quick local startup and stability.

## UI and editor update
- Added a YouTube video-link search mode. Paste a standard watch, youtu.be, embed, or Shorts URL to load its thumbnail through the YouTube Data API.
- Added subtle fade-in animation for result cards and retained the animated loading status/progress indicator.
- Removed the verbose empty-gallery explanation and shortened status/footer copy.
- Simplified the editor header and actions to three primary tools: Remove Objects, Auto Adjust, and Enhance Quality.
- Added optional on-demand Real-ESRGAN x4 enhancement in a separate local Python environment. It crops proportionally to 16:9 and exports a 1920x1080 working image; it never stretches the source.
- Big-LaMa object removal remains optional and on demand. AI runtimes/models are not bundled with the main app.
- Version remains 1.0.0. This is a local-debug package; no EXE or GitHub release was created.

- Auto Adjust now performs one-click, content-aware correction: adaptive tonal-range/exposure balancing, restrained white balance, shadow/highlight recovery, vibrance and subtle sharpening. It runs locally with the app dependencies, does not download an AI model, and supports Undo/Reset.
