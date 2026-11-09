# Optional local AI engines

## Remove Objects

Remove Objects uses SAM 2.1 Hiera Tiny for box-prompted object segmentation and Big-LaMa for background reconstruction. Both are local, cached on demand, and reused by a persistent worker process. This feature does not expose extra LaMa tools or change Auto Adjust / Enhance.

## Enhance

Enhance remains a separate optional Real-ESRGAN workflow. Its runtime and model cache are independent of object removal.
