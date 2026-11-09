# Object-removal model setup

The **Remove Objects** tool uses two local models in sequence:

1. **SAM 2.1 Hiera Tiny** turns the user's rectangle into an object mask.
2. **Big-LaMa** fills the masked region using surrounding image context.

The models are downloaded on first use and cached locally. A separate Python 3.11 environment is prepared for the AI stack so the main app's Python 3.14 environment is not modified. The worker keeps both models loaded during the app session. CUDA is used automatically when a compatible NVIDIA GPU is available; otherwise the models run on CPU.

The rectangle is a segmentation prompt, not a rectangular hole. The final composite uses the predicted object mask, leaving pixels outside that mask unchanged. All processing is local; images are not uploaded.

SAM 2.1 model: adaptive SAM 2.1 Hiera (Large on GPUs with sufficient free VRAM; Base Plus/Small on lower-memory accelerators; Tiny on CPU) via Hugging Face Transformers. Inpainting: Big-LaMa via `simple-lama-inpainting`.
