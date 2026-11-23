from base64 import b64decode
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
import re

import requests
from PIL import Image, ImageChops, ImageDraw

from .studio import image_bytes, open_image

FLUX_URL = "https://api.cloudflare.com/client/v4/accounts/{}/ai/run/@cf/black-forest-labs/{}"
CLOUD_MODELS = {
    "4b": ("flux-2-klein-4b", (512, 288)),
    "9b": ("flux-2-klein-9b", (1024, 576)),
}

def cloud_references(references):
    prepared = []
    for role, path in references:
        if path:
            image = open_image(Path(path).read_bytes())
            image.thumbnail((511, 511), Image.Resampling.LANCZOS)
            prepared.append((role, image_bytes(image)))
    return prepared


def cloud_image(account, token, prompt, references=(), model="4b"):
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account) or not token:
        raise ValueError("Add your Cloudflare account ID and Workers AI token in Settings.")
    roles = " ".join(f"Attached image {index + 1} is the {role}."
                     for index, (role, _) in enumerate(references))
    name, (width, height) = CLOUD_MODELS[model]
    fields = {"prompt": (None, f"{prompt.strip()} {roles}".strip()),
              "width": (None, str(width)), "height": (None, str(height))}
    for index, (_, image) in enumerate(references):
        fields[f"input_image_{index}"] = (f"reference-{index + 1}.png", image, "image/png")
    try:
        response = requests.post(FLUX_URL.format(account, name), headers={"Authorization": f"Bearer {token}"},
                                 files=fields, timeout=(6, 90), allow_redirects=False)
    except requests.RequestException:
        raise ValueError("Could not reach Cloudflare Workers AI.") from None
    if response.status_code in (402, 429):
        raise ValueError("Cloudflare rejected the request due to quota or rate limits. Check your Workers AI dashboard.")
    if not response.ok:
        raise ValueError(f"Cloudflare returned HTTP {response.status_code}. Check the Workers AI token and account.")
    try:
        if response.headers.get("Content-Type", "").startswith("image/"):
            data = response.content
        else:
            data = b64decode(response.json()["result"]["image"], validate=True)
        open_image(data)
    except (ValueError, KeyError, TypeError, OSError):
        raise ValueError("Cloudflare did not return a valid draft image.") from None
    return data


def mask_image(size, mode, points, brush, mask=None):
    if mask is None:
        mask = Image.new("L", size)
    draw = ImageDraw.Draw(mask)
    pixels = [(round(x * size[0]), round(y * size[1])) for x, y in points]
    if mode == "box":
        (x1, y1), (x2, y2) = pixels
        draw.rectangle((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), fill=255)
    else:
        diameter = max(2, round(brush * size[0]))
        radius = diameter // 2
        draw.line(pixels, fill=255, width=diameter, joint="curve")
        for x, y in pixels:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    return mask


def combined_mask(size, selections):
    mask = Image.new("L", size)
    for mode, points, brush in selections:
        mask_image(size, mode, points, brush, mask)
    return mask


def repair_masks(size, selections):
    # Isolate distant marks so each repair uses the model's full input resolution.
    groups = []
    gap = max(24, size[0] // 16)
    for selection in selections:
        mask = mask_image(size, *selection)
        if not mask.getbbox():
            continue
        index = 0
        while index < len(groups):
            left, top, right, bottom = mask.getbbox()
            x1, y1, x2, y2 = groups[index].getbbox()
            nearby = (left <= x2 + gap and right + gap >= x1 and top <= y2 + gap and bottom + gap >= y1)
            if nearby:
                mask = ImageChops.lighter(mask, groups.pop(index))
                index = 0
            else:
                index += 1
        groups.append(mask)
    return groups


def save_draft(root, prompt, folder, index, data):
    if folder is None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "_" + uuid4().hex[:8]
        folder = root / stamp
        folder.mkdir(parents=True)
    (folder / f"{index}.png").write_bytes(image_bytes(open_image(data)))
    temporary = folder / "batch.tmp"
    temporary.write_text(json.dumps({"prompt": prompt, "count": index + 1}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(folder / "batch.json")
    return folder


def batches(root):
    for path in sorted(root.glob("*/batch.json"), reverse=True):
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
            count = info["count"]
            if 1 <= count <= 3 and all((path.parent / f"{index}.png").is_file() for index in range(count)):
                yield path.parent, info["prompt"], count
        except (OSError, ValueError, KeyError, TypeError):
            continue
