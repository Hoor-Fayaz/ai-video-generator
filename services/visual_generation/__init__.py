"""Modular visual generation service with replaceable providers and high-end video clip support."""

import os
from typing import Callable, List, Optional

from .base import (
    VisualGenerationProvider,
    VisualGenerationRequest,
    VisualGenerationResult,
    validate_generated_media,
)
from .pexels_video_generator import PexelsVideoGenerator
from .replicate_video_generator import ReplicateVideoGenerator
from .huggingface_generator import HuggingFaceGenerator
from .replicate_generator import ReplicateGenerator
from .local_image_generator import LocalImageGenerator
from .mock_generator import MockVisualGenerator
from .motion_video_generator import create_cinematic_motion_clip
from .prompt_builder import build_consistency_context, build_image_prompt

# Singleton provider instances
_pexels_video = PexelsVideoGenerator()
_replicate_video = ReplicateVideoGenerator()
_huggingface = HuggingFaceGenerator()
_replicate = ReplicateGenerator()
_local = LocalImageGenerator()
_mock = MockVisualGenerator()

__all__ = [
    "VisualGenerationService",
    "VisualGenerationProvider",
    "VisualGenerationRequest",
    "VisualGenerationResult",
    "get_visual_provider",
    "build_image_prompt",
    "build_consistency_context",
    "create_cinematic_motion_clip",
]


def get_visual_provider(force: Optional[str] = None) -> VisualGenerationProvider:
    """
    Resolve active visual generation provider with high-end video clip priority.

    VISUAL_PROVIDER env / force options:
      - auto (default): Pexels HD video -> Replicate AI video/image -> Hugging Face -> local -> mock
      - pexels / pexels_video / stock_video: Require Pexels/Pixabay HD video clips
      - replicate_video: Require Replicate AI video generator
      - replicate: Require Replicate image generator (Flux)
      - huggingface: Require Hugging Face free inference API
      - local: Require local model
      - mock: Development mock
    """
    mode = (force or os.getenv("VISUAL_PROVIDER", "auto")).lower().strip()

    if mode in ["pexels", "pexels_video", "stock_video"]:
        if not _pexels_video.is_available:
            raise RuntimeError(
                f"Pexels Video provider unavailable: {_pexels_video.availability_message()}"
            )
        return _pexels_video

    if mode in ["replicate_video", "ai_video"]:
        if not _replicate_video.is_available:
            raise RuntimeError(
                f"Replicate Video provider unavailable: {_replicate_video.availability_message()}"
            )
        return _replicate_video

    if mode == "mock":
        return _mock

    if mode == "huggingface":
        if not _huggingface.is_available:
            raise RuntimeError(
                f"Hugging Face provider unavailable: {_huggingface.availability_message()}"
            )
        return _huggingface

    if mode == "replicate":
        if not _replicate.is_available:
            raise RuntimeError(
                f"Replicate provider unavailable: {_replicate.availability_message()}"
            )
        return _replicate

    if mode == "local":
        if not _local.is_available:
            raise RuntimeError(
                f"Local visual provider unavailable: {_local.availability_message()}"
            )
        return _local

    # Auto mode: Prioritize high-end video clips where possible
    if _pexels_video.is_available:
        print(f"[VisualGen] Using Pexels HD Video Provider: {_pexels_video.name}")
        return _pexels_video

    if _replicate.is_available:
        # If user explicitly configured video model, use replicate_video
        if os.getenv("REPLICATE_VIDEO_MODEL"):
            print(f"[VisualGen] Using Replicate AI Video Provider: {_replicate_video.name}")
            return _replicate_video
        print(f"[VisualGen] Using Replicate Provider: {_replicate.name}")
        return _replicate

    if _huggingface.is_available:
        print(f"[VisualGen] Using Hugging Face provider: {_huggingface.name}")
        return _huggingface

    if _local.is_available:
        print(f"[VisualGen] Using local provider: {_local.name}")
        return _local

    print(f"[VisualGen] All cloud providers unavailable. Using mock provider.")
    return _mock


class VisualGenerationService:
    """Orchestrates scene visual and video clip generation with seamless fallback."""

    def __init__(self, provider: Optional[VisualGenerationProvider] = None):
        self._provider = provider
        self._fallback_used = False
        self._fallback_reason: Optional[str] = None

    @property
    def provider(self) -> VisualGenerationProvider:
        if self._provider is None:
            self._provider = get_visual_provider()
        return self._provider

    @property
    def fallback_used(self) -> bool:
        return self._fallback_used

    @property
    def fallback_reason(self) -> Optional[str]:
        return self._fallback_reason

    def generate_scene(
        self,
        request: VisualGenerationRequest,
        on_status: Optional[Callable[[int, str], None]] = None,
    ) -> VisualGenerationResult:
        """Generate a scene clip or image, with intelligent auto-fallback chain."""
        if on_status:
            on_status(request.scene_number, "generating")

        result = self.provider.generate(request)

        # Fallback chain: Pexels Video -> Replicate Video -> Replicate Flux -> Hugging Face -> Local -> Mock
        if not result.success and not isinstance(self.provider, MockVisualGenerator):
            self._fallback_used = True
            self._fallback_reason = result.error_message
            print(f"[VisualGen] {self.provider.name} failed for scene {request.scene_number}: {result.error_message}. Cascading fallback...")

            chain = []
            if isinstance(self.provider, PexelsVideoGenerator):
                chain = [_replicate_video, _replicate, _huggingface, _local, _mock]
            elif isinstance(self.provider, ReplicateVideoGenerator):
                chain = [_replicate, _huggingface, _local, _mock]
            elif isinstance(self.provider, ReplicateGenerator):
                chain = [_huggingface, _local, _mock]
            elif isinstance(self.provider, HuggingFaceGenerator):
                chain = [_replicate, _local, _mock]
            elif isinstance(self.provider, LocalImageGenerator):
                chain = [_mock]

            for next_p in chain:
                if next_p.is_available or isinstance(next_p, MockVisualGenerator):
                    print(f"[VisualGen] Attempting fallback with {next_p.name}...")
                    self._provider = next_p
                    result = next_p.generate(request)
                    if result.success:
                        result.metadata["fallback_from"] = self.provider.name
                        result.metadata["fallback_reason"] = self._fallback_reason
                        break

        # Convert static image to cinematic motion video clip if requested / needed
        if result.success:
            ext = os.path.splitext(result.output_path)[1].lower()
            if ext in [".png", ".jpg", ".jpeg", ".webp"]:
                # If output is an image, also create an animated video clip .mp4 for the scene
                clip_out = os.path.splitext(result.output_path)[0] + ".mp4"
                ok = create_cinematic_motion_clip(
                    image_path=result.output_path,
                    output_path=clip_out,
                    duration=request.duration or 5.0,
                    width=request.width,
                    height=request.height,
                    fps=30,
                    scene_index=request.scene_number - 1,
                )
                if ok and os.path.exists(clip_out):
                    result.metadata["video_clip_path"] = clip_out
                    # If caller prefers video or in auto mode, update output_path to the motion video clip
                    if request.media_type in ["auto", "video"]:
                        result.output_path = clip_out
                        result.media_type = "video"

        if on_status:
            on_status(request.scene_number, "completed" if result.success else "failed")

        return result
