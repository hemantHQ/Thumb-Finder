import argparse
from PIL import Image, ImageOps
import torch
import sys
import torchvision.transforms.functional as tv_functional
sys.modules.setdefault('torchvision.transforms.functional_tensor', tv_functional)
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer
import numpy as np

p=argparse.ArgumentParser()
p.add_argument('--input',required=True); p.add_argument('--output',required=True); p.add_argument('--model',required=True)
a=p.parse_args()

def crop_black_borders(image):
    """Trim only clearly uniform black bars around the image, not dark scene content."""
    arr=np.asarray(image.convert('RGB'))
    gray=arr.mean(axis=2)
    h,w=gray.shape
    row_limit=max(2,int(w*0.012))
    col_limit=max(2,int(h*0.012))
    top=0; bottom=h; left=0; right=w
    while top < h//5 and np.mean(gray[top] < 14) > 0.985: top+=1
    while bottom > h*4//5 and np.mean(gray[bottom-1] < 14) > 0.985: bottom-=1
    while left < w//5 and np.mean(gray[:,left] < 14) > 0.985: left+=1
    while right > w*4//5 and np.mean(gray[:,right-1] < 14) > 0.985: right-=1
    if top>row_limit or h-bottom>row_limit or left>col_limit or w-right>col_limit:
        if right-left >= w*0.55 and bottom-top >= h*0.55:
            return image.crop((left,top,right,bottom))
    return image

def run(device_name):
    device=torch.device(device_name)
    model=RRDBNet(num_in_ch=3,num_out_ch=3,num_feat=64,num_block=23,num_grow_ch=32,scale=4)
    up=RealESRGANer(scale=4,model_path=a.model,model=model,tile=256,tile_pad=8,pre_pad=0,
                    half=(device.type=='cuda'),device=device)
    img=Image.open(a.input).convert('RGB')
    img=crop_black_borders(img)
    # A 640x360 inference input is sufficient for a 1920x1080 export and avoids
    # generating a huge 4x intermediate that must immediately be discarded.
    img=ImageOps.fit(img,(640,360),method=Image.Resampling.LANCZOS,centering=(0.5,0.5))
    bgr=np.asarray(img)[:,:,::-1].copy()
    out,_=up.enhance(bgr,outscale=2)
    Image.fromarray(out[:,:,::-1]).resize((1920,1080),Image.Resampling.LANCZOS).save(a.output)

try:
    run('cuda' if torch.cuda.is_available() else 'cpu')
except Exception as exc:
    if not torch.cuda.is_available():
        raise
    # Retry on CPU if a driver, CUDA kernel, or VRAM issue breaks acceleration.
    torch.cuda.empty_cache()
    run('cpu')
