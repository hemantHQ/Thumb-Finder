from pathlib import Path
from secrets import randbits, token_hex
from time import monotonic
from urllib.parse import urlsplit

import requests

from .studio import image_bytes, open_image

DEFAULT_SERVER = "http://127.0.0.1:8188"
SETUP_URL = "https://docs.comfy.org/tutorials/flux/flux-2-klein"
MODEL = "flux-2-klein-4b-fp8.safetensors"
ENCODER = "qwen_3_4b.safetensors"
VAE = "flux2-vae.safetensors"
CONCEPTS = ("Close-up of the lead actor with a strong expression.",
            "Medium shot framing a dramatic confrontation.",
            "Wide action shot with a clear focal subject.")


def server_url(value):
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    local = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if (not parsed.hostname or parsed.username is not None or parsed.query or parsed.fragment
            or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))):
        raise ValueError("Use a local HTTP URL or an HTTPS URL for your ComfyUI server.")
    return value


def workflow(prompt, images, seed):
    width, height = 1024, 576
    conditioning = ["4", 0]
    graph = {}

    def node(key, class_type, **inputs):
        graph[key] = {"class_type": class_type, "inputs": inputs}
        return [key, 0]

    model = node("1", "UNETLoader", unet_name=MODEL, weight_dtype="default")
    encoder = node("2", "CLIPLoader", clip_name=ENCODER, type="flux2", device="default")
    vae = node("3", "VAELoader", vae_name=VAE)
    node("4", "CLIPTextEncode", clip=encoder, text=prompt)
    for index, name in enumerate(images, 20):
        pixels = node(str(index * 3), "LoadImage", image=name)
        latent = node(str(index * 3 + 1), "VAEEncode", pixels=pixels, vae=vae)
        conditioning = node(str(index * 3 + 2), "ReferenceLatent", conditioning=conditioning, latent=latent)
    latent = node("5", "EmptyFlux2LatentImage", width=width, height=height, batch_size=1)
    schedule = node("6", "Flux2Scheduler", steps=4, width=width, height=height)
    guider = node("7", "BasicGuider", model=model, conditioning=conditioning)
    sampler = node("8", "KSamplerSelect", sampler_name="euler")
    noise = node("9", "RandomNoise", noise_seed=seed)
    samples = node("10", "SamplerCustomAdvanced", noise=noise, guider=guider, sampler=sampler,
                   sigmas=schedule, latent_image=latent)
    decoded = node("11", "VAEDecode", samples=samples, vae=vae)
    node("12", "PreviewImage", images=decoded)
    return graph


class ComfyUI:
    def __init__(self, server, stop, session):
        self.server = server_url(server)
        self.stop = stop
        self.session = session

    def call(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self.server + path, timeout=(4, 15),
                                            allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise ValueError("Could not reach ComfyUI. Start it and check the server URL in Settings.") from None
        if not 200 <= response.status_code < 300:
            if path == "/prompt" and response.status_code == 400:
                try:
                    body = response.json()
                    errors = [error for node in body.get("node_errors", {}).values()
                              for error in node.get("errors", [])]
                    detail = (errors[0].get("details") or errors[0].get("message")) if errors else ""
                except (AttributeError, KeyError, TypeError, ValueError):
                    detail = ""
                raise ValueError("ComfyUI rejected the workflow. Check that the model files and current ComfyUI are installed."
                                 + (f" {detail[:170]}" if detail else ""))
            raise ValueError(f"ComfyUI returned HTTP {response.status_code}. Check the server URL and setup.")
        return response

    def upload(self, path):
        image = open_image(Path(path).read_bytes())
        image.thumbnail((1024, 1024))
        filename = f"thumb-finder-{token_hex(8)}.png"
        result = self.call("POST", "/upload/image",
                           files={"image": (filename, image_bytes(image), "image/png")},
                           data={"type": "input", "subfolder": "thumb-finder"}).json()
        return "/".join(filter(None, (result.get("subfolder"), result["name"])))

    def generate(self, prompt, references, count):
        names, roles = [], []
        self.call("GET", "/system_stats")
        for role, path in references:
            if path:
                names.append(self.upload(path))
                roles.append(f"Reference {len(names)} is the {role}.")
        base = " ".join((prompt, *roles, "Cinematic 16:9 movie thumbnail, clear focal subject."))
        for concept in CONCEPTS if count == 3 else ("",):
            if self.stop.is_set():
                return
            yield self.render(f"{base} {concept}".strip(), names)

    def render(self, prompt, references):
        graph = workflow(prompt, references, randbits(63))
        result = self.call("POST", "/prompt", json={"prompt": graph, "client_id": token_hex(16)}).json()
        job = result.get("prompt_id")
        if not job:
            raise ValueError("ComfyUI did not return a job ID.")
        deadline = monotonic() + 900
        while monotonic() < deadline and not self.stop.wait(1):
            item = self.call("GET", f"/history/{job}").json().get(job, {})
            if item.get("status", {}).get("status_str") == "error":
                messages = item["status"].get("messages", [])
                details = next((data.get("exception_message", "") for kind, data in messages
                                if kind == "execution_error"), "")
                raise ValueError("ComfyUI could not render this image." + (f" {details[:180]}" if details else ""))
            images = item.get("outputs", {}).get("12", {}).get("images", [])
            if images:
                image = images[0]
                params = {"filename": image["filename"], "subfolder": image.get("subfolder", ""),
                          "type": image.get("type", "temp")}
                data = self.call("GET", "/view", params=params).content
                open_image(data)
                return data
            if item.get("status", {}).get("completed"):
                raise ValueError("ComfyUI finished without returning a preview image.")
        if self.stop.is_set():
            return None
        raise ValueError("ComfyUI took too long. Check its queue before trying again.")
