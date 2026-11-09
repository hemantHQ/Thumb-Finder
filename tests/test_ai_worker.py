from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_worker_uses_sam21_and_lama_only_for_removal():
    source = (ROOT / "thumb_finder" / "ai_worker.py").read_text(encoding="utf-8")
    assert "facebook/sam2.1-hiera-large" in source
    assert "Sam2Processor" in source and "Sam2Model" in source
    assert "SimpleLama" in source
    assert "StableDiffusionInpaintPipeline" not in source
    assert "diffusers" not in source.lower()


def test_worker_caches_both_models_in_process():
    source = (ROOT / "thumb_finder" / "ai_worker.py").read_text(encoding="utf-8")
    assert "_SAM_MODEL = None" in source
    assert "_LAMA = None" in source
    assert 'parser.add_argument("--server"' in source


def test_editor_uses_box_prompt_not_grabcut():
    source = (ROOT / "thumb_finder" / "editor.py").read_text(encoding="utf-8")
    assert '"box": [x, y, x+w, y+h]' in source
    assert "cv2.grabCut" not in source
    assert "transformers==5.2.0" in source
    assert "simple-lama-inpainting==0.1.2" in source


def test_editor_reuses_persistent_worker():
    source = (ROOT / "thumb_finder" / "editor.py").read_text(encoding="utf-8")
    assert "_worker_process = None" in source
    assert '"--server"' in source
    assert 'HF_HOME' in source


def test_text_removal_keeps_disconnected_glyph_components():
    source = (ROOT / "thumb_finder" / "ai_worker.py").read_text(encoding="utf-8")
    assert "Text is naturally made of disconnected letters" in source
    assert "selected |= component" in source


def test_enhance_runtime_uses_defined_runtime_root():
    source = (ROOT / "thumb_finder" / "editor.py").read_text(encoding="utf-8")
    assert "base_python=_compatible_ai_python(env.parent)" in source
    assert "_compatible_ai_python(base)" not in source


def test_enhance_preserves_nonstandard_aspect_ratio_without_cropping():
    source = (ROOT / "thumb_finder" / "editor.py").read_text(encoding="utf-8")
    assert "ImageOps.contain(enhanced, (1920,1080)" in source
    assert "enhanced.crop" not in source
