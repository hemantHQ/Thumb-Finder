from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
import csv
import re
import shutil
import uuid

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat

SIZE = (1280, 720)
FHD = (1920, 1080)
ADJUSTMENTS = ("Brightness", "Contrast", "Highlights", "Shadows", "Temperature",
               "Tint", "Saturation", "Vibrance", "Clarity", "Sharpness")


@dataclass
class Edit:
    crop: int = 50
    vertical: int = 50
    zoom: int = 100
    text: str = ""
    quality: int = 94
    values: dict = field(default_factory=dict)
    repaired: bytes = b""
    enhanced: bool = False


@dataclass
class Candidate:
    source: bytes = b""
    filename: str = ""
    edit: Edit = field(default_factory=Edit)
    undo: list = field(default_factory=list)
    redo: list = field(default_factory=list)

    def change(self, edit):
        if self.edit != edit:
            self.undo.append(self.edit)
            del self.undo[:-80]
            self.redo.clear()
            self.edit = edit

    def step(self, backwards):
        origin, destination = (self.undo, self.redo) if backwards else (self.redo, self.undo)
        if origin:
            destination.append(self.edit)
            self.edit = origin.pop()


def open_image(data):
    with Image.open(BytesIO(data)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def auto_adjust(data):
    image = open_image(data)
    image.thumbnail((320, 320))
    luma = image.convert("L")
    gray = ImageStat.Stat(luma)
    histogram = luma.histogram()
    def percentile(fraction):
        target = sum(histogram) * fraction
        seen = 0
        for level, count in enumerate(histogram):
            seen += count
            if seen >= target:
                return level
        return 255
    dark, middle, bright = (percentile(fraction) for fraction in (0.1, 0.5, 0.95))
    return {
        "Brightness": max(-12, min(16, round((123 - middle) / 5))),
        "Contrast": max(0, min(12, round((155 - (bright - dark)) / 9))) if gray.stddev[0] > 12 else 0,
        "Highlights": -max(0, round((bright - 175) / 4)),
        "Shadows": max(0, round((60 - dark) / 3)),
        "Vibrance": 6,
        "Sharpness": 6,
    }


def render(source, edit, size=SIZE, original=False):
    if edit.repaired and not original:
        image = open_image(edit.repaired).resize(size, Image.Resampling.LANCZOS)
    else:
        image = crop_source(source, edit, size)
    if original:
        return image
    return apply_adjustments(image, edit, size)


def crop_source(source, edit, size):
    image = open_image(source)
    width, height = image.size
    factor = min(width / size[0], height / size[1]) * 100 / edit.zoom
    crop_width, crop_height = size[0] * factor, size[1] * factor
    left = (width - crop_width) * edit.crop / 100
    top = (height - crop_height) * edit.vertical / 100
    return image.resize(size, Image.Resampling.LANCZOS, box=(left, top, left + crop_width, top + crop_height))


def apply_adjustments(image, edit, size):
    values = edit.values
    for name, enhancer in (("Brightness", ImageEnhance.Brightness), ("Contrast", ImageEnhance.Contrast),
                           ("Saturation", ImageEnhance.Color), ("Sharpness", ImageEnhance.Sharpness)):
        if values.get(name):
            image = enhancer(image).enhance(1 + values[name] / 100)
    shadows = values.get("Shadows", 0)
    highlights = values.get("Highlights", 0)
    warmth = values.get("Temperature", 0) * 0.45
    tint = values.get("Tint", 0) * 0.3
    if any((shadows, highlights, warmth, tint)):
        lookup = []
        for bias in (warmth + tint, -tint, -warmth + tint):
            for level in range(256):
                t = level / 255
                delta = 1.8 * (shadows * (1 - t) ** 2 + highlights * t ** 2) * t * (1 - t)
                lookup.append(max(0, min(255, round(level + delta + bias))))
        image = image.point(lookup)
    vibrance = values.get("Vibrance", 0)
    if vibrance:
        red, green, blue = image.split()
        from PIL import ImageChops
        maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        minimum = ImageChops.darker(ImageChops.darker(red, green), blue)
        mask = ImageOps.invert(ImageChops.subtract(maximum, minimum))
        image = Image.composite(ImageEnhance.Color(image).enhance(1 + vibrance / 100), image, mask)
    clarity = values.get("Clarity", 0)
    if clarity > 0:
        image = image.filter(ImageFilter.UnsharpMask(max(1, size[0] // 160), clarity, 4))
    elif clarity < 0:
        image = Image.blend(image, image.filter(ImageFilter.GaussianBlur(2)), -clarity / 160)
    if edit.text.strip():
        draw = ImageDraw.Draw(image)
        text = edit.text.strip()
        stroke = max(1, size[0] // 250)
        for pixels in range(size[0] // 11, 8, -2):
            font = ImageFont.load_default(size=pixels)
            if draw.textlength(text, font=font) <= size[0] * 0.9:
                break
        draw.text((size[0] // 2, int(size[1] * 0.92)), text, anchor="ms", font=font,
                  fill="white", stroke_width=stroke, stroke_fill="#111111")
    return image


def image_bytes(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def save_jpeg(candidate, path):
    size = FHD if candidate.edit.enhanced else SIZE
    render(candidate.source, candidate.edit, size).save(
        path, "JPEG", quality=candidate.edit.quality, optimize=True, progressive=True)
    with Image.open(path) as result:
        if result.size != size or result.format != "JPEG":
            raise ValueError("The saved image failed JPEG validation.")
        result.verify()
    return size


def download(candidate, path):
    path = Path(path)
    temporary = path.with_name(f".thumb-finder-{uuid.uuid4().hex}.tmp")
    try:
        size = save_jpeg(candidate, temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return size


def export(candidates, directory, project):
    if len(candidates) != 3 or not all(candidate.source for candidate in candidates):
        raise ValueError("Load an image into each of A, B and C before exporting.")
    safe = re.sub(r'[^\w -]+', '', project).strip()[:65] or "Untitled movie"
    project_dir = Path(directory) / f"Movie - {safe}"
    project_dir.mkdir(parents=True, exist_ok=True)
    run = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    staging = project_dir / f".{run}.partial"
    final = project_dir / run
    staging.mkdir()
    try:
        with (staging / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(("Candidate", "File", "Source", "Width", "Height", "Quality", "Bytes"))
            for label, candidate in zip("ABC", candidates):
                path = staging / f"{label}.jpg"
                size = save_jpeg(candidate, path)
                source = candidate.filename
                if source and source[0] in "=+-@\t\r\n":
                    source = "'" + source
                writer.writerow((label, path.name, source, *size, candidate.edit.quality, path.stat().st_size))
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging)
        raise
    return final
