"""Run the downloaded models within the optional Python environment."""
import sys


def repair_region(image, selection, reconstruct):
    from PIL import Image, ImageFilter

    box = selection.getbbox()
    if not box:
        return image
    margin = max(2, min(5, round(image.width / 400)))
    fill_mask = selection.filter(ImageFilter.MaxFilter(2 * margin + 1))
    left, top, right, bottom = fill_mask.getbbox()
    span = max(right - left, bottom - top)
    width, height = image.size
    # Large removals need the composition and scene geometry of the full frame.
    wide_repair = (right - left >= width * 0.27 or bottom - top >= height * 0.4)
    side = max(image.size) if wide_repair else max(320, round(span * 2.0) + 48)

    def axis(low, high, size):
        if side >= size:
            return 0, size
        start = min(max(0, (low + high - side) // 2), size - side)
        return start, start + side

    x1, x2 = axis(left, right, image.width)
    y1, y2 = axis(top, bottom, image.height)
    context = image.crop((x1, y1, x2, y2))
    local_mask = fill_mask.crop((x1, y1, x2, y2))
    side = max(context.size)
    offset = ((side - context.width) // 2, (side - context.height) // 2)
    # Extend edge pixels where the source is narrower than the model's square input.
    square = Image.new("RGB", (side, side))
    x, y = offset
    if y:
        square.paste(context.crop((0, 0, context.width, 1)).resize((side, y)), (0, 0))
    if y + context.height < side:
        height = side - y - context.height
        square.paste(context.crop((0, context.height - 1, context.width, context.height)).resize((side, height)),
                     (0, y + context.height))
    if x:
        square.paste(context.crop((0, 0, 1, context.height)).resize((x, side)), (0, 0))
    if x + context.width < side:
        width = side - x - context.width
        square.paste(context.crop((context.width - 1, 0, context.width, context.height)).resize((width, side)),
                     (x + context.width, 0))
    square.paste(context, offset)
    model_mask = Image.new("L", square.size)
    model_mask.paste(local_mask, offset)
    resized_mask = model_mask.resize((512, 512), Image.Resampling.BILINEAR).point(lambda level: 255 if level > 8 else 0)
    prediction = reconstruct(square.resize((512, 512), Image.Resampling.LANCZOS), resized_mask)
    patch = prediction.resize(square.size, Image.Resampling.LANCZOS).crop(
        (x, y, x + context.width, y + context.height))
    patch = match_repair_edges(patch, context, local_mask)
    # Fill every marked pixel fully and feather only the narrow surrounding boundary.
    blend = local_mask.filter(ImageFilter.GaussianBlur(0.8))
    blend.paste(255, mask=selection.crop((x1, y1, x2, y2)))
    image.paste(patch, (x1, y1), blend)
    return image


def match_repair_edges(patch, context, mask):
    from PIL import ImageChops, ImageFilter, ImageStat

    collar = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(17)), mask)
    if not collar.getbbox():
        return patch
    reference = ImageStat.Stat(context, collar).median
    prediction = ImageStat.Stat(patch, collar).median
    differences = [int(wanted - actual) for wanted, actual in zip(reference, prediction)]
    if max(map(abs, differences)) > 22:
        return patch
    # Compensate for small model color shifts measured just outside the repair.
    lut = [max(0, min(255, level + round(delta * 0.65)))
           for delta in differences for level in range(256)]
    return patch.point(lut)


def finish_enhancement(upscaled, original):
    from PIL import Image, ImageEnhance, ImageOps, ImageStat

    size = (1920, 1080)
    clean = upscaled.resize(size, Image.Resampling.LANCZOS)
    baseline = original.resize(size, Image.Resampling.LANCZOS)
    # The source contribution keeps skin and film grain from looking overly processed.
    clean = Image.blend(clean, baseline, 0.20)
    probe = clean.resize((160, 90), Image.Resampling.BOX).convert("L")
    levels = ImageStat.Stat(probe)
    if levels.stddev[0] < 8:
        return clean
    light = levels.mean[0]
    gain = 1 + max(-0.035, min(0.10, (112 - light) / 600))
    curve = [max(0, min(255, round(level + (gain - 1) * level * (1 - level / 256))))
             for level in range(256)]
    clean = clean.point(curve * 3)
    stretch = ImageOps.autocontrast(clean, cutoff=0.5, preserve_tone=True)
    if 55 <= light <= 185:
        clean = Image.blend(clean, stretch, 0.12)
    return ImageEnhance.Color(clean).enhance(1.035)


def main():
    packages, tool, model, source, output, *masks = sys.argv[1:]
    sys.path.insert(0, packages)

    import numpy as np
    import onnxruntime as ort
    from PIL import Image

    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(model, sess_options=options, providers=["CPUExecutionProvider"])
    with Image.open(source) as file:
        image = file.convert("RGB")

    def rgb_tensor(picture):
        return (np.asarray(picture, dtype=np.float32) / 255).transpose(2, 0, 1)[None].copy()

    def picture(tensor, multiplier):
        pixels = (tensor[0].transpose(1, 2, 0) * multiplier).clip(0, 255).round().astype(np.uint8)
        return Image.fromarray(pixels)

    if tool == "remove":
        def reconstruct(context, resized_mask):
            mask_data = np.asarray(resized_mask, dtype=np.float32)[None, None] / 255
            result = session.run(None, {"image": rgb_tensor(context), "mask": mask_data})[0]
            return picture(result, 1)

        for path in masks:
            with Image.open(path) as file:
                selection = file.convert("L")
            image = repair_region(image, selection, reconstruct)
    else:
        width, height = image.size
        upscale = Image.new("RGB", (width * 2, height * 2))
        stride, padding = 256, 24
        for y in range(0, height, stride):
            for x in range(0, width, stride):
                end_x, end_y = min(x + stride, width), min(y + stride, height)
                left, top = max(0, x - padding), max(0, y - padding)
                box = (left, top, min(end_x + padding, width), min(end_y + padding, height))
                tile = session.run(None, {"input": rgb_tensor(image.crop(box))})[0]
                valid = tuple(value * 2 for value in (x - left, y - top, end_x - left, end_y - top))
                upscale.paste(picture(tile, 255).crop(valid), (x * 2, y * 2))
        image = finish_enhancement(upscale, image)
    image.save(output)


if __name__ == "__main__":
    main()
