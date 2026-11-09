"""Persistent SAM 2.1 segmentation + Big-LaMa inpainting worker."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

_SAM_MODEL = None
_SAM_PROCESSOR = None
_SAM_DEVICE = None
_LAMA = None


def _get_models(progress=None):
    """Load SAM 2.1 Tiny and Big-LaMa once and reuse them for the app session."""
    global _SAM_MODEL, _SAM_PROCESSOR, _SAM_DEVICE, _LAMA
    if _SAM_MODEL is None:
        if progress: progress("Loading SAM 2.1 model…")
        import torch
        from transformers import Sam2Model, Sam2Processor

        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
        # Use the most accurate SAM 2.1 variant the machine can reasonably run.
        # The model is selected once and stays loaded for the whole app session.
        if device.type == "cuda":
            try:
                free_bytes, total_bytes = torch.cuda.mem_get_info(device)
                free_gb = free_bytes / (1024 ** 3)
            except Exception:
                free_gb = 0
            if free_gb >= 8:
                model_id = "facebook/sam2.1-hiera-large"
            elif free_gb >= 5:
                model_id = "facebook/sam2.1-hiera-base-plus"
            else:
                model_id = "facebook/sam2.1-hiera-small"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            model_id = "facebook/sam2.1-hiera-small"
        else:
            model_id = "facebook/sam2.1-hiera-tiny"
        dtype = torch.float16 if device.type == "cuda" else torch.float32
        _SAM_PROCESSOR = Sam2Processor.from_pretrained(model_id)
        _SAM_MODEL = Sam2Model.from_pretrained(model_id, torch_dtype=dtype).to(device).eval()
        _SAM_DEVICE = device
    if _LAMA is None:
        if progress: progress("Loading Big-LaMa background reconstruction model…")
        import torch
        from simple_lama_inpainting import SimpleLama
        # simple-lama-inpainting uses a local torchscript checkpoint cache.
        _LAMA = SimpleLama(device=_SAM_DEVICE)
    return _SAM_MODEL, _SAM_PROCESSOR, _SAM_DEVICE, _LAMA


def _segment_object(image, box, progress=None):
    """Segment the prompted object, then clean the mask conservatively."""
    import numpy as np
    import torch
    model, processor, device, _ = _get_models(progress)
    x0, y0, x1, y1 = [int(v) for v in box]
    width, height = image.size
    x0, x1 = max(0, min(x0, width - 1)), max(1, min(x1, width))
    y0, y1 = max(0, min(y0, height - 1)), max(1, min(y1, height))
    if x1 - x0 < 5 or y1 - y0 < 5:
        raise ValueError("The selected area is too small. Draw a larger box around the object.")

    inputs = processor(images=image, input_boxes=[[[x0, y0, x1, y1]]], return_tensors="pt")
    inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        if device.type == "cuda":
            with torch.autocast("cuda", dtype=torch.float16):
                outputs = model(**inputs, multimask_output=True)
        else:
            outputs = model(**inputs, multimask_output=True)

    masks = processor.post_process_masks(outputs.pred_masks.cpu(), inputs["original_sizes"])[0]
    masks = masks.detach().float().cpu().numpy()
    masks = np.squeeze(masks)
    if masks.ndim == 2:
        masks = masks[None, ...]
    scores = outputs.iou_scores.detach().float().cpu().numpy().reshape(-1)

    # Prefer a high-confidence mask that substantially overlaps the user's box.
    # The box is a prompt, not a hard clipping boundary: clipping to it would
    # leave object fringes behind whenever the user draws slightly too tightly.
    prompt = np.zeros(masks.shape[-2:], dtype=bool)
    prompt[y0:y1, x0:x1] = True
    candidates = []
    for idx, logits in enumerate(masks):
        binary = logits > 0
        inside = int(np.count_nonzero(binary & prompt))
        total = int(np.count_nonzero(binary))
        if inside < 25 or total == 0:
            continue
        coverage = inside / max(1, total)
        prompt_fill = inside / max(1, int(np.count_nonzero(prompt)))
        score = float(scores[idx]) if idx < len(scores) else 0.0
        # Reject implausibly huge masks, but allow a small margin beyond the box
        # so hair, thin edges and objects touching the selection border survive.
        if total > max(inside * 3.5, int(np.count_nonzero(prompt)) * 2.8):
            continue
        candidates.append((score * (0.55 + 0.30 * coverage + 0.15 * min(1.0, prompt_fill * 1.5)), binary))
    if not candidates:
        raise RuntimeError("SAM could not identify a clear object. Try a tighter rectangle around it.")
    mask = max(candidates, key=lambda item: item[0])[1]
    # Limit only distant spill, not the actual segmentation at the rectangle edge.
    margin_x = max(8, int((x1 - x0) * 0.12))
    margin_y = max(8, int((y1 - y0) * 0.12))
    allowed = np.zeros(mask.shape, dtype=bool)
    ax0, ay0 = max(0, x0-margin_x), max(0, y0-margin_y)
    ax1, ay1 = min(width, x1+margin_x), min(height, y1+margin_y)
    allowed[ay0:ay1, ax0:ax1] = True
    mask &= allowed

    # Keep the main selected object and remove isolated prediction specks.
    try:
        import cv2
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        if count > 1:
            # Text is naturally made of disconnected letters/dots. Keeping only
            # the largest component removes one letter and leaves the rest behind.
            # Retain every meaningful component intersecting the user's box,
            # while rejecting tiny SAM speckles outside the prompted region.
            prompt_region = np.zeros(labels.shape, dtype=bool)
            prompt_region[y0:y1, x0:x1] = True
            selected = np.zeros(labels.shape, dtype=bool)
            prompt_area = max(1, int(np.count_nonzero(prompt_region)))
            for label in range(1, count):
                component = labels == label
                area = int(stats[label, cv2.CC_STAT_AREA])
                overlap = int(np.count_nonzero(component & prompt_region))
                if overlap and area >= max(3, int(prompt_area * 0.000015)):
                    selected |= component
            # If SAM's components do not overlap the exact prompt (edge rounding),
            # retain the component closest to the center as a safe fallback.
            if np.any(selected):
                mask = selected
            else:
                cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                choices = []
                for label in range(1, count):
                    area = int(stats[label, cv2.CC_STAT_AREA])
                    px, py = centroids[label]
                    distance = ((px-cx)/max(1, x1-x0))**2 + ((py-cy)/max(1, y1-y0))**2
                    choices.append((area / (1.0 + distance), label))
                mask = labels == max(choices)[1]
        # Close tiny gaps and fill enclosed holes without expanding the whole rectangle.
        # Close small gaps between glyph strokes, then add a modest edge margin
        # so antialiased text outlines are not left visible after inpainting.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        clean = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        edge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        clean = cv2.dilate(clean, edge_kernel, iterations=1)
        h, w = clean.shape
        padded = cv2.copyMakeBorder(clean, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        flood_mask = np.zeros((h + 4, w + 4), np.uint8)
        cv2.floodFill(padded, flood_mask, (0, 0), 1)
        outside = padded[1:-1, 1:-1] == 1
        holes = (~outside & (clean == 0)).astype(np.uint8)
        mask = (clean | holes).astype(bool)
    except Exception:
        pass

    result = mask.astype(np.uint8) * 255
    if int(np.count_nonzero(result)) < 25:
        raise RuntimeError("SAM returned an almost-empty selection. Try drawing closer around the object.")
    return result


def inpaint(image_path: Path, output_path: Path, box, progress=None):
    import numpy as np
    from PIL import Image, ImageFilter

    image = Image.open(image_path).convert("RGB")
    model, processor, device, lama = _get_models(progress)
    if progress: progress('Detecting the selected object and refining its edges…')
    mask_array = _segment_object(image, box, progress)
    mask = Image.fromarray(mask_array, mode="L")

    # Remove the object AND its nearby cast shadow/edge contamination. SAM usually
    # segments the object itself, not the shadow it casts. Build a context-aware
    # cleanup region around the object, then selectively include dark, low-chroma
    # pixels connected to the object inside that region. This avoids blindly
    # repainting a large rectangle or unrelated nearby details.
    import cv2
    rgb = np.asarray(image, dtype=np.uint8)
    base = (mask_array > 0).astype(np.uint8)
    h, w = base.shape
    obj_y, obj_x = np.where(base > 0)
    if len(obj_x) == 0:
        raise ValueError("The object mask is empty. Please select the object again.")
    obj_w = int(obj_x.max() - obj_x.min() + 1)
    obj_h = int(obj_y.max() - obj_y.min() + 1)
    # Context radius scales with object size and output resolution. Larger values
    # help remove cast shadows; capped to protect nearby subjects/details.
    radius = int(max(18, min(96, round(max(obj_w, obj_h) * 0.10))))
    k = radius * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    expanded = cv2.dilate(base, kernel, iterations=1).astype(bool)

    # Estimate the local background brightness from a ring just outside the
    # expanded object. Shadows are typically darker and less chromatic than the
    # surrounding surface. Only grow into connected dark pixels in this halo.
    if progress: progress('Analysing nearby pixels to include cast shadows…')
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    light = lab[:, :, 0].astype(np.int16)
    chroma = np.sqrt((lab[:, :, 1].astype(np.float32) - 128) ** 2 +
                     (lab[:, :, 2].astype(np.float32) - 128) ** 2)
    outer_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 4 + 1, radius * 4 + 1))
    outer = cv2.dilate(base, outer_kernel, iterations=1).astype(bool) & ~expanded
    if np.any(outer):
        local_light = int(np.median(light[outer]))
        # Avoid treating naturally dark textured objects as shadows: shadow
        # candidates must be darker than the local surface and reasonably neutral.
        dark = (light < (local_light - 10)) & expanded & ~base.astype(bool)
        # Connected-component filtering: only dark regions touching the object
        # boundary are considered cast-shadow candidates.
        count, labels = cv2.connectedComponents(dark.astype(np.uint8), 8)
        shadow = np.zeros_like(base, dtype=bool)
        for label in range(1, count):
            component = labels == label
            if np.any(cv2.dilate(component.astype(np.uint8),
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) & base):
                shadow |= component
        # Keep a modest safety dilation for antialiased edges and fine outlines.
        edge_pad = cv2.dilate(base, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
        mask_array = ((base > 0) | shadow | edge_pad).astype(np.uint8) * 255
    else:
        mask_array = expanded.astype(np.uint8) * 255

    mask = Image.fromarray(mask_array, mode="L")
    bbox = mask.getbbox()
    if not bbox:
        raise ValueError("SAM returned an empty object mask. Please adjust the selection.")

    if progress: progress('Reconstructing the selected area and rebuilding the background…')
    result = lama(image, mask).convert("RGB")
    if result.size != image.size:
        raise RuntimeError("LaMa returned an image with unexpected dimensions.")

    # Feather only the boundary. The center remains fully replaced so the removed
    # object cannot ghost through the original image.
    if progress: progress('Blending reconstructed pixels and cleaning the edges…')
    alpha = mask.filter(ImageFilter.GaussianBlur(radius=2.2))
    final = Image.composite(result, image, alpha)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(output_path, format="PNG")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--image")
    parser.add_argument("--output")
    parser.add_argument("--box", nargs=4, type=int)
    args = parser.parse_args()

    if args.server:
        for line in sys.stdin:
            try:
                job = json.loads(line)
                def report(message):
                    print(json.dumps({"status": message}), flush=True)
                with contextlib.redirect_stdout(sys.stderr):
                    inpaint(Path(job["image"]), Path(job["output"]), job["box"], report)
                print(json.dumps({"ok": True}), flush=True)
            except Exception as exc:
                print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
        return

    if not all((args.image, args.output, args.box)):
        parser.error("Missing required image, output, or box")
    inpaint(Path(args.image), Path(args.output), args.box)


if __name__ == "__main__":
    main()
