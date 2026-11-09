from pathlib import Path


def test_sam_and_lama_models_are_cached_outside_the_app():
    source = (Path(__file__).parents[1] / "thumb_finder" / "editor.py").read_text(encoding="utf-8")
    worker = (Path(__file__).parents[1] / "thumb_finder" / "ai_worker.py").read_text(encoding="utf-8")
    assert '"Models" / "huggingface"' in source
    assert '"Models" / "torch"' in source
    assert "facebook/sam2.1-hiera-large" in worker


def test_ai_runtime_is_pinned_and_uses_transformers_sam2():
    source = (Path(__file__).parents[1] / "thumb_finder" / "editor.py").read_text(encoding="utf-8")
    assert "transformers==5.2.0" in source
    assert "simple-lama-inpainting==0.1.2" in source
    assert "from transformers import Sam2Model, Sam2Processor" in source
