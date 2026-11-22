# Thumb Finder v1.0

A PySide6 desktop studio for finding movie thumbnails and preparing three distinct YouTube A/B/C candidates.

## Run from source

Install Python 3.12 or 3.13, then run:

```sh
python -m pip install -r requirements.txt
python run_app.py
```

On Windows, double-click **Run_Thumb_Finder_Debug.bat** after installing dependencies. The launcher uses a local `.venv` if present.

## Search and edit

1. In **Settings**, add a project key with YouTube Data API v3 enabled. You may supply a second key for quota failover. Environment variables `YOUTUBE_API_KEY_1` and `YOUTUBE_API_KEY_2` also work.
2. Search for a movie or actor or paste a YouTube video URL. Category adds a query keyword. Discovery uses a 40-minute minimum in the background and direct URLs accept any duration. A reference image ranks the fetched results by visual similarity.
3. Use **Save** to keep the highest available source or **Edit** to send it to A, B or C. The studio also accepts local files and works offline.
4. Adjust each candidate independently. Crop, tone, optional text and JPEG quality are per candidate. Use **Small preview** to check readability and **Before adjustments** to compare the current crop.
5. Use **Download A**, **Download B**, or **Download C** to save the active candidate as a JPG. For a full set, enter a movie name and select **Export A/B/C** to create a unique run directory with three JPGs and a CSV manifest. Candidates export at 1280 × 720 by default or 1920 × 1080 after Enhance.

## Optional offline editing

**Auto Adjust** runs in Thumb Finder and balances exposure, shadows, highlights and color. Inspect the result with **Before adjustments** and fine-tune it with the sliders.

1. In **Remove**, choose **Rectangle** or **Brush**. On first use approve the **LaMa** download (about 208 MB). Mark the object or text, review the purple mask, and choose **Apply removal**. Combine brush and rectangle marks as needed. **Undo mark** and **Clear** change the mask before applying. **Undo** reverts an applied removal.
2. Select **Enhance** and approve the **Real-ESRGAN** download (about 68 MB) on first use. The app then enhances the selected candidate to 1920 × 1080.

The first model also installs the shared ONNX Runtime engine. Thumb Finder handles setup in the background and caches the engine and each model in its local app data. Subsequent edits run offline on your computer, and your images stay on the device. The packaged runtime targets Apple Silicon with macOS 14 or later. Windows source launches reuse the Python installation that started Thumb Finder.

Set the crop before running local AI. The edits remain reversible, and **Manual adjustments** opens the sliders and text controls. Undo or reset the AI edit to change its crop. Model sources: [LaMa ONNX](https://huggingface.co/Carve/LaMa-ONNX) and [Real-ESRGAN ONNX](https://huggingface.co/SceneWorks/real-esrgan-onnx).

## Create online with Cloudflare

1. Use a Cloudflare **Workers Free** account and create a Workers AI API token. In Thumb Finder **Settings**, enter the Cloudflare account ID and token. You can also supply the token through the `CLOUDFLARE_API_TOKEN` environment variable.
2. In **Create**, leave **Cloudflare · Online** selected and enter a prompt. This option sends the prompt to Cloudflare and uses FLUX.1 Schnell with four generation steps.
3. Each draft appears and is saved as it finishes. **Stop after current** ends a three-concept batch after its current image. Use **Draft history** to reopen saved batches and **Reuse prompt** to make another variation. Each draft has a 16:9 preview and **Send to Edit** for A, B, or C. The full generated image remains available when adjusting its crop in Edit.

Cloudflare shares its 10,000 daily free Neurons across Workers AI usage on the account. Image size and generation steps affect usage, so the number of images available varies. A free plan stops requests when its free allocation runs out. [Cloudflare setup](https://developers.cloudflare.com/workers-ai/get-started/rest-api/) · [Cloudflare pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)

## Optional local Create with reference images

Create uses the Apache 2.0 FLUX.2 Klein 4B model through a separately installed ComfyUI. There is no generation API key, credit balance, or per-image fee. Your computer or your studio's own ComfyUI server supplies the compute. Search still uses a separate YouTube Data API key.

1. Install or update [ComfyUI](https://www.comfy.org/download). In the [FLUX.2 Klein setup guide](https://docs.comfy.org/tutorials/flux/flux-2-klein), use the **distilled 4B** model files. Put them in these folders under ComfyUI:
   - `models/diffusion_models/flux-2-klein-4b-fp8.safetensors`
   - `models/text_encoders/qwen_3_4b.safetensors`
   - `models/vae/flux2-vae.safetensors`
2. Start ComfyUI. Thumb Finder defaults to `http://127.0.0.1:8188`. If ComfyUI displays a different local port, enter its address in **Settings → ComfyUI server**. A studio-hosted endpoint can use HTTPS.
3. In **Create**, choose **ComfyUI · Local** and enter a prompt. You can add a composition or cast reference, or both. Choose **1 draft** or **3 concepts** and click **Generate**. The three-concept mode queues a close-up, confrontation, and wide action shot.
4. Choose an A/B/C destination on a draft and use **Send to Edit**. Local drafts render at 1024 × 576.

The model files and ComfyUI runtime are separate downloads and stay installed across Thumb Finder updates. Generation speed and compatibility depend on the ComfyUI machine, especially available GPU memory. Reference files are transferred to the ComfyUI server and stored in its input folder.

## Apple Silicon packaging

One arm64 build targets both Mac mini M4 and M6. The workflow builds on a macOS 15 arm64 runner, signs the bundle ad hoc through PyInstaller, and includes the Thumb Finder icon in Finder and the Dock. Before uploading, it extracts the resulting ZIP, checks the executable architecture, validates the code signature and icon, and opens the packaged app through the native Qt macOS platform to check startup and preview rendering.

### Publish using GitHub Desktop

1. In GitHub Desktop, open your existing local `hemantHQ/Thumb-Finder` repository or use **File → Clone repository**. Copy the contents of the extracted source folder into the clone, including `.github`.
2. Review **Changes**, commit to the intended branch, and click **Push origin**. If you are working on a separate branch, merge it into the default branch before running the workflow from the Actions page.
3. In the browser, go to **Actions → Build Thumb Finder for Apple Silicon → Run workflow**. Select the default branch and keep **Publish the verified ZIP to Releases from the default branch** checked. After both jobs pass, download `Thumb-Finder-v1.0-macOS-arm64.zip` from **Releases → Assets**. A push of the `v1.0` tag also publishes after verification.
4. Uncheck the publish option for an artifact-only test build. You can download the ZIP from the successful run under **Artifacts**. Test the exact ZIP on each Mac you list as tested. The automatic publish job preserves an existing release asset and checks that the tag points to the verified commit.

### Install on a Mac

Extract the ZIP, drag **Thumb Finder.app** into **Applications**, and open it there. Ad-hoc signing allows the native Apple Silicon code to load. Apple Gatekeeper can still show a first-launch warning for an unnotarized download. If you trust and have verified this build, try opening it once and use **System Settings → Privacy & Security → Open Anyway** if Apple offers it. If the app actually launches and then quits unexpectedly, save the macOS crash report so the startup failure can be diagnosed. [Apple's app-opening guidance](https://support.apple.com/en-us/102445)

Only manual artifact-only builds can embed the optional YouTube secrets. These values can be recovered from the resulting bundle. Release builds use credentials entered in the app's Settings. GitHub's update check opens Releases for manual installation.

## Checks

```sh
python -m compileall -q run_app.py thumb_finder tests
python -m unittest discover -s tests
```
