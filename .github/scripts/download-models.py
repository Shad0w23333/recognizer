"""Download the original CI models with the project's installed Hub package."""

from importlib.metadata import version

from huggingface_hub import snapshot_download


print(f"Downloading CI models with huggingface-hub {version('huggingface-hub')}", flush=True)
# Keep the dependency version resolved with recognizer instead of upgrading it
# independently of transformers/tokenizers. These models are public.
snapshot_download(repo_id="flavour/CLIP-ViT-B-16-DataComp.XL-s13B-b90K", token=False, max_workers=2)
snapshot_download(repo_id="CIDAS/clipseg-rd64-refined", token=False, max_workers=2)
