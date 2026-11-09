# Thumb Finder — Local Debug Version

Thumb Finder is a PySide6 desktop app for discovering popular long-form movie thumbnails from YouTube. This package is for local source debugging only. It does not build an EXE, contact GitHub Releases, or perform online updates. Version remains **v1.0**.

## Run on Windows

1. Extract the project folder somewhere writable.
2. Install the main app dependencies: `py -m pip install -r requirements.txt`.
3. Run `Run_Thumb_Finder_Debug.bat` or `py run_app.py`.
4. Enter your YouTube Data API key when prompted. It is stored in `%USERPROFILE%\.thumb_finder\config.json`.

The launcher does not build an EXE or install AI dependencies.

## Features

- Search by actor name, normal topic, or reference thumbnail image.
- Movie/Film & Animation category search with a 40-minute minimum by default.
- Genre keyword filter and view-count ordering of fetched candidates.
- Auto-load more candidates while scrolling.
- Light/dark theme; system appearance is the initial default.
- Save original available YouTube thumbnail files.
- Thumbnail editor with rectangle selection, resize handles, Auto Adjust, brightness, contrast, saturation, Undo and Save edited copy.

## Optional AI object removal

The main app starts without an AI model or PyTorch. The first time the user clicks **Remove Objects**, Thumb Finder asks permission to install a separate PyTorch/LaMa runtime and download the Big-LaMa model. The model itself is a small download; PyTorch is the larger dependency. Both are cached outside the app and reused.

- Big-LaMa is used only for object removal. Auto Adjust and Enhance remain separate.
- A persistent helper process loads the model once per app session and reuses it for subsequent removals.
- The user's rectangle guides object segmentation; LaMa fills the estimated object mask, not the entire rectangle.
- No compiler is installed or invoked. If compatible prebuilt PyTorch wheels are unavailable, removal reports an error while the main app remains usable.
- Images are processed locally and are never uploaded. The original thumbnail is not overwritten.

See [ON_DEMAND_AI_ENGINE.md](ON_DEMAND_AI_ENGINE.md) for model and cache details.

## Logs and settings

- Settings: `%USERPROFILE%\.thumb_finder\config.json`
- Logs: `%USERPROFILE%\.thumb_finder\logs\thumb_finder.log`

The YouTube API key is stored in the local config file in plain text. Keep that file private.

## Limitations

- YouTube does not expose actual CTR for arbitrary videos. View count is used for popularity ordering.
- Genre filtering is keyword-based because YouTube does not provide reliable movie-genre metadata for search results.
- The YouTube API's `videoDuration=long` filter means over 20 minutes; the app separately checks the exact 40-minute minimum after retrieving video details.
- AI inpainting reconstructs content plausibly; it cannot guarantee perfect recovery of hidden details, especially on complex backgrounds.

## Important: object-removal engine identity

This source package uses **SAM 2.1 + Big-LaMa** for Remove Objects. The runtime worker is `thumb_finder/ai_worker.py`; it does not use Stable Diffusion, Diffusers, or a tokenizer. If a dialog says `Local Stable Diffusion removal failed` or asks for `tokenizer/added_tokens.json`, that dialog is coming from an older running copy of Thumb Finder, not this source package. Close every Thumb Finder process, extract this ZIP into a new folder, and launch `Run_Thumb_Finder_Debug.bat` from that new folder. Do not copy old `thumb_finder` files over this folder.


## Automatic GitHub builds (Windows + macOS)

The workflow `.github/workflows/release-build.yml` runs whenever a version tag is pushed.
It builds three separate downloads:

- Windows x64
- macOS Intel (x86_64)
- macOS Apple Silicon (arm64)

To publish a release, push a tag from the repository root:

```bash
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions runs the tests, builds all three platforms, and attaches the ZIP files to
the matching GitHub Release. The version embedded in each build is read from the tag.
You can also start a test build from the Actions tab using **workflow_dispatch**.

## One-file remote live switch and version control

Edit only `release-control.json` on the GitHub `main` branch:

- `enabled: true` — app may start.
- `enabled: false` — app is remotely disabled at next launch.
- `latest_version` — version to show as available.
- `minimum_version` — older builds below this version are blocked and sent to the release page.
- `message` — message shown to users.
- `release_url` — page opened for update/blocked versions.

The app fetches this file at startup. If GitHub is unreachable, it fails open and lets the
app start; a network outage therefore does not accidentally disable the app. The check uses
a short timeout. This is an availability/version switch, not DRM or a tamper-proof security
boundary: users can bypass it in a modified local build. Changes to the JSON file do not
require a new app build.
