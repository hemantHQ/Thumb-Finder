# Thumb Finder v1.0.0 — workflow improvements

## Search
- Reduced search choices to exactly **Search** and **Via photo**.
- Text search uses one input for actor names, movie titles and topics.
- A local heuristic selects actor-style vs topic-style query wording; YouTube results remain the source of truth.
- Genre filtering is optional and stays collapsed until the user opens it.
- Photo search ranks candidate thumbnails using a blend of colour histogram, perceptual hash and ORB local-feature matching.

## Editing and export
- Thumbnail downloads are normalized to RGB JPEG before saving.
- Editor input is normalized to JPEG.
- Export is JPG-only at quality 95.
- Existing SAM 2.1 + LaMa object removal remains in place. It can reconstruct plausible background texture, but cannot guarantee recovery of content fully hidden behind removed text (for example, an occluded hand). That requires generative inpainting and can produce invented details.
- Photo search does not identify a person's identity from a face. It uses visual similarity; any genre/category interpretation is only a broad hint, not authoritative metadata.

## Enhance
- Enhancement readiness checks now use the same cross-platform runtime/model paths as the worker.
- Cached Real-ESRGAN runtime and weights are reused when import checks pass.
- The enhancement worker continues to use the isolated AI runtime; the app's main Python environment is not modified.

## Validation
- Python compileall passed.
- 14 existing automated tests passed.
- Actual YouTube API search, AI inference, and Real-ESRGAN GPU/CPU processing still require validation on the target PC.
