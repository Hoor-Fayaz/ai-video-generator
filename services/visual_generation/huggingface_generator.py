"""Hugging Face Inference API provider using official huggingface_hub.InferenceClient."""

import os
import re
from typing import Optional
from dotenv import load_dotenv
from PIL import Image, ImageOps
from huggingface_hub import InferenceClient

from .base import VisualGenerationProvider, VisualGenerationRequest, VisualGenerationResult, validate_generated_image
from .prompt_builder import NEGATIVE_PROMPT, build_image_prompt, build_dynamic_negative_prompt, validate_visual_prompt_grounding

# Load environment variables
load_dotenv()


def _get_api_key() -> Optional[str]:
    """Get Hugging Face API key from environment."""
    return os.getenv("HUGGINGFACE_API_KEY")


def _get_model_id() -> str:
    """Get the Hugging Face model to use."""
    return os.getenv("HUGGINGFACE_MODEL", "black-forest-labs/FLUX.1-schnell").strip()


def _is_flux_model(model_id: str) -> bool:
    """FLUX models don't support negative_prompt."""
    return "flux" in model_id.lower()


# Ordered fallback chain of free HuggingFace models
_FALLBACK_MODELS = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "runwayml/stable-diffusion-v1-5",
]


def _redact_token(text: str) -> str:
    """Redact any API tokens or bearer headers from error strings."""
    if not text:
        return ""
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", text)
    cleaned = re.sub(r"hf_[A-Za-z0-9_]+", "[REDACTED_KEY]", cleaned)
    return cleaned


class HuggingFaceGenerator(VisualGenerationProvider):
    """
    Hugging Face Inference API provider using official huggingface_hub.InferenceClient.
    
    Uses InferenceClient(provider="auto", api_key=...) for Serverless Inference Providers.
    Requires HUGGINGFACE_API_KEY environment variable.
    """

    @property
    def name(self) -> str:
        return f"huggingface:{_get_model_id()}"

    @property
    def is_available(self) -> bool:
        api_key = _get_api_key()
        if not api_key:
            return False
        try:
            return len(api_key) > 5 and not api_key.startswith("your_")
        except Exception:
            return False

    def availability_message(self) -> str:
        api_key = _get_api_key()
        if not api_key:
            return "Hugging Face API key not found. Set HUGGINGFACE_API_KEY environment variable."
        return f"Hugging Face provider ready using model: {_get_model_id()}"

    def generate(self, request: VisualGenerationRequest) -> VisualGenerationResult:
        api_key = _get_api_key()
        if not api_key:
            return VisualGenerationResult(
                success=False,
                output_path=request.output_path,
                provider_name=self.name,
                is_mock=False,
                error_message="Hugging Face API key not configured"
            )

        os.makedirs(os.path.dirname(request.output_path) or ".", exist_ok=True)

        is_valid, val_reason = validate_visual_prompt_grounding(
            topic=request.topic,
            claim=request.claim,
            narration=request.narration,
            visual_prompt=request.visual_prompt,
        )

        # Build topic-locked structured diffusion prompt
        prompt = build_image_prompt(
            visual_prompt=request.visual_prompt,
            environment=request.environment,
            characters=request.characters,
            objects=request.objects,
            camera_style=request.camera_style,
            visual_style=request.visual_style,
            consistency_context=request.consistency_context,
            topic=request.topic,
            claim=request.claim,
            narration=request.narration,
        )

        # Build dynamic negative prompt based on topic
        neg_prompt = request.negative_prompt or build_dynamic_negative_prompt(
            topic=request.topic or request.visual_prompt,
            claim=request.claim,
            visual_style=request.visual_style,
        )

        # Debug logging for every scene (Requirement 11)
        print(f"\n[Scene Visual Grounding] Scene {request.scene_number}:")
        print(f"  Topic: {request.topic or 'N/A'}")
        print(f"  Claim: {request.claim or 'N/A'}")
        print(f"  Narration: {request.narration or 'N/A'}")
        print(f"  Visual prompt: {request.visual_prompt}")
        print(f"  Validation result: {'PASSED' if is_valid else f'REPAIRED ({val_reason})'}")

        try:
            primary_model = _get_model_id()
            client = InferenceClient(provider="auto", api_key=api_key)

            # 9:16 vertical resolution — closest supported sizes for major models
            gen_width = 576
            gen_height = 1024

            img = None
            last_error = None
            models_to_try = [primary_model] + [m for m in _FALLBACK_MODELS if m != primary_model]

            for model_id in models_to_try:
                try:
                    kwargs = dict(
                        prompt=prompt,
                        model=model_id,
                        width=gen_width,
                        height=gen_height,
                    )
                    # FLUX models do not support negative_prompt
                    if not _is_flux_model(model_id) and neg_prompt:
                        kwargs["negative_prompt"] = neg_prompt

                    print(f"[HuggingFace] Generating scene {request.scene_number} with {model_id}...")
                    img = client.text_to_image(**kwargs)
                    if img and isinstance(img, Image.Image):
                        print(f"[HuggingFace] ✓ Generated with {model_id}")
                        break
                except Exception as e_m:
                    last_error = str(e_m)
                    err_lower = last_error.lower()
                    if any(k in err_lower for k in ["402", "payment", "credits", "quota", "rate limit", "503"]):
                        print(f"[HuggingFace] {model_id} unavailable ({last_error[:60]}), trying next model...")
                        # Switch to serverless client for next attempt
                        client = InferenceClient(api_key=api_key)
                        continue
                    else:
                        raise e_m

            if img is None:
                raise RuntimeError(f"All HuggingFace models failed. Last error: {last_error}")

            if not isinstance(img, Image.Image):
                return VisualGenerationResult(
                    success=False,
                    output_path=request.output_path,
                    provider_name=self.name,
                    is_mock=False,
                    error_message="Hugging Face client did not return a valid PIL Image"
                )

            orig_w, orig_h = img.size

            # Resize/fit to request output resolution (1080x1920) without stretching
            if img.size != (request.width, request.height):
                img = ImageOps.fit(img, (request.width, request.height), method=Image.LANCZOS)

            img.save(request.output_path, format="PNG", optimize=True)

            is_valid, val_err = validate_generated_image(
                request.output_path, target_width=request.width, target_height=request.height
            )
            if not is_valid:
                return VisualGenerationResult(
                    success=False,
                    output_path=request.output_path,
                    provider_name=self.name,
                    is_mock=False,
                    error_message=f"Hugging Face image validation failed: {val_err}"
                )

            return VisualGenerationResult(
                success=True,
                output_path=request.output_path,
                provider_name=self.name,
                is_mock=False,
                metadata={
                    "prompt": prompt,
                    "model": model_id,
                    "original_size": f"{orig_w}x{orig_h}",
                    "final_size": f"{request.width}x{request.height}",
                    "aspect_ratio": "9:16",
                }
            )

        except Exception as e:
            err_str = _redact_token(str(e))
            return VisualGenerationResult(
                success=False,
                output_path=request.output_path,
                provider_name=self.name,
                is_mock=False,
                error_message=f"Hugging Face generation error: {err_str}"
            )