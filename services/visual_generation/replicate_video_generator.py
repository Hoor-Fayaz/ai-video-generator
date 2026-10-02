"""Replicate AI Video Generation Provider for generating cinematic video clips."""

import os
import time
import requests
from typing import Optional
from dotenv import load_dotenv

from .base import (
    VisualGenerationProvider,
    VisualGenerationRequest,
    VisualGenerationResult,
    validate_generated_video,
)
from .prompt_builder import NEGATIVE_PROMPT, build_image_prompt

load_dotenv()


def _get_api_key() -> Optional[str]:
    return os.getenv("REPLICATE_API_KEY")


def _get_video_model() -> str:
    # Supported models: bytedance/animatediff-lightning-4-step, lucataco/animate-diff, minimax/video-01
    return os.getenv("REPLICATE_VIDEO_MODEL", "bytedance/animatediff-lightning-4-step")


class ReplicateVideoGenerator(VisualGenerationProvider):
    """
    Generates genuine AI video clips (.mp4) using Replicate's hosted video models.
    """

    @property
    def name(self) -> str:
        return f"replicate_video:{_get_video_model()}"

    @property
    def is_available(self) -> bool:
        key = _get_api_key()
        return bool(key and len(key.strip()) > 20)

    def availability_message(self) -> str:
        if not self.is_available:
            return "Replicate API key missing or invalid. Set REPLICATE_API_KEY in .env."
        return f"Replicate AI Video Provider ready using model: {_get_video_model()}"

    def generate(self, request: VisualGenerationRequest) -> VisualGenerationResult:
        api_key = _get_api_key()
        if not api_key:
            return VisualGenerationResult(
                success=False,
                output_path=request.output_path,
                provider_name=self.name,
                is_mock=False,
                error_message="Replicate API key not configured"
            )

        base_out = os.path.splitext(request.output_path)[0]
        video_out = base_out + ".mp4"
        os.makedirs(os.path.dirname(video_out) or ".", exist_ok=True)

        model_id = _get_video_model()
        prompt = request.video_motion_prompt or request.visual_prompt
        if not prompt:
            prompt = build_image_prompt(
                visual_prompt=request.visual_prompt,
                environment=request.environment,
                characters=request.characters,
                objects=request.objects,
                camera_style=request.camera_style,
                visual_style=request.visual_style,
                consistency_context=request.consistency_context,
            )

        # Enhance prompt for cinematic motion
        enhanced_prompt = f"{prompt}, cinematic camera movement, photorealistic, 4k ultra high definition documentary, perfectly stable framing, smooth motion"

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }

        # Build appropriate model payload
        payload_input = {
            "prompt": enhanced_prompt,
            "negative_prompt": NEGATIVE_PROMPT,
        }

        if "animatediff" in model_id.lower():
            payload_input["steps"] = 4 if "lightning" in model_id.lower() else 25
            payload_input["guidance_scale"] = 1.0 if "lightning" in model_id.lower() else 7.5
        elif "minimax" in model_id.lower():
            payload_input["prompt_optimizer"] = True

        url = f"https://api.replicate.com/v1/models/{model_id}/predictions"

        try:
            print(f"[Replicate Video] Submitting video generation request for scene {request.scene_number}...")
            resp = requests.post(url, headers=headers, json={"input": payload_input}, timeout=30)
            if resp.status_code not in [200, 201]:
                return VisualGenerationResult(
                    success=False,
                    output_path=video_out,
                    provider_name=self.name,
                    is_mock=False,
                    error_message=f"Replicate API error: {resp.status_code} - {resp.text[:200]}"
                )

            data = resp.json()
            prediction_url = data.get("urls", {}).get("get")
            if not prediction_url:
                return VisualGenerationResult(
                    success=False,
                    output_path=video_out,
                    provider_name=self.name,
                    is_mock=False,
                    error_message="Missing prediction polling URL from Replicate"
                )

            # Poll for completion
            max_wait = 240  # up to 4 minutes
            start_time = time.time()
            video_download_url = None

            while time.time() - start_time < max_wait:
                time.sleep(4)
                stat_resp = requests.get(prediction_url, headers=headers, timeout=15)
                if stat_resp.status_code == 200:
                    stat_data = stat_resp.json()
                    status = stat_data.get("status")
                    if status == "succeeded":
                        out = stat_data.get("output")
                        if isinstance(out, list) and len(out) > 0:
                            video_download_url = out[0]
                        elif isinstance(out, str):
                            video_download_url = out
                        break
                    elif status in ["failed", "canceled"]:
                        return VisualGenerationResult(
                            success=False,
                            output_path=video_out,
                            provider_name=self.name,
                            is_mock=False,
                            error_message=f"Replicate video generation failed: {stat_data.get('error')}"
                        )

            if not video_download_url:
                return VisualGenerationResult(
                    success=False,
                    output_path=video_out,
                    provider_name=self.name,
                    is_mock=False,
                    error_message=f"Video generation timed out after {max_wait}s"
                )

            # Download video
            print(f"[Replicate Video] Downloading completed AI video clip...")
            with requests.get(video_download_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(video_out, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)

            is_valid, reason = validate_generated_video(video_out)
            if not is_valid:
                return VisualGenerationResult(
                    success=False,
                    output_path=video_out,
                    provider_name=self.name,
                    is_mock=False,
                    error_message=f"Downloaded video failed validation: {reason}"
                )

            return VisualGenerationResult(
                success=True,
                output_path=video_out,
                provider_name=self.name,
                media_type="video",
                is_mock=False,
                metadata={"video_url": video_download_url, "model": model_id}
            )

        except Exception as e:
            return VisualGenerationResult(
                success=False,
                output_path=video_out,
                provider_name=self.name,
                is_mock=False,
                error_message=f"Replicate Video request exception: {str(e)}"
            )
