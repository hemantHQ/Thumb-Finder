"""Create platform icon files from the Thumb Finder brand mark."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path("build_icons")
OUT.mkdir(exist_ok=True)

def render(size: int) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = max(2, size // 32)
    d.rounded_rectangle((m, m, size-m, size-m), radius=size*0.23,
                        fill=(102, 87, 232, 255))
    # Magnifier ring and handle
    cx, cy, r = size*0.44, size*0.42, size*0.22
    sw = max(3, size//15)
    d.ellipse((cx-r, cy-r, cx+r, cy+r), outline="white", width=sw)
    d.line((size*.60, size*.60, size*.79, size*.79), fill="white", width=sw, joint="curve")
    # Small sparkle inside the lens
    points = [(size*.44,size*.27),(size*.48,size*.39),(size*.60,size*.43),
              (size*.48,size*.47),(size*.44,size*.59),(size*.40,size*.47),
              (size*.28,size*.43),(size*.40,size*.39)]
    d.polygon(points, fill=(255,255,255,245))
    return im

sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
for s in sizes:
    render(s).save(OUT / f"icon_{s}.png")
render(256).save("thumb_finder/app_icon.ico", format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
iconset = OUT / "ThumbFinder.iconset"
iconset.mkdir(exist_ok=True)
for s in [16,32,64,128,256,512]:
    render(s).save(iconset / f"icon_{s}x{s}.png")
    render(s*2).save(iconset / f"icon_{s}x{s}@2x.png")
