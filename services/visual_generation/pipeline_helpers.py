"""Helpers for integrating visual generation into the video pipeline."""

import os
from datetime import datetime
from typing import Callable, Optional

from services.visual_generation import VisualGenerationService, build_consistency_context
from services.visual_generation.base import VisualGenerationRequest, validate_generated_image
from services.visual_generation.prompt_builder import (
    validate_visual_prompt_grounding,
    regenerate_grounded_visual_prompt,
)


def init_visual_status(scenes: list) -> dict:
    """Initialize visual generation status tracker."""
    return {
        "total_scenes": len(scenes),
        "current_scene": 0,
        "provider": None,
        "fallback_used": False,
        "fallback_reason": None,
        "scenes": {
            str(s.get("scene_number", i + 1)): {
                "status": "pending",
                "scene_number": s.get("scene_number", i + 1),
            }
            for i, s in enumerate(scenes)
        },
        "updated_at": datetime.utcnow().isoformat(),
    }


def update_scene_status(status: dict, scene_number: int, state: str) -> dict:
    """Update a single scene's visual generation status."""
    key = str(scene_number)
    if key not in status["scenes"]:
        status["scenes"][key] = {"scene_number": scene_number}
    status["scenes"][key]["status"] = state
    if state == "generating":
        status["current_scene"] = scene_number
    status["updated_at"] = datetime.utcnow().isoformat()
    return status


def scene_image_path(base_dir: str, scene_number: int) -> str:
    return os.path.join(base_dir, f"scene_{scene_number:03d}.png")


def scene_image_url(video_id: int, scene_number: int) -> str:
    return f"/assets/video_{video_id}/scene_{scene_number:03d}.png"


def generate_scene_visuals(
    video_id: int,
    scenes: list,
    base_dir: str,
    visual_style: str,
    db_session,
    video_model,
    scene_asset_model,
    width: int = 1080,
    height: int = 1920,
    status_callback: Optional[Callable[[dict], None]] = None,
    visual_provider: Optional[str] = None,
) -> tuple[list[str], list, dict]:
    """
    Generate visuals (video clips or images) for all scenes, persist SceneAsset records, update plan.

    Returns (media_paths, updated_scenes, visual_status).
    """
    os.makedirs(base_dir, exist_ok=True)
    from . import get_visual_provider
    prov = get_visual_provider(force=visual_provider) if visual_provider else None
    service = VisualGenerationService(provider=prov)
    visual_status = init_visual_status(scenes)
    visual_status["provider"] = service.provider.name

    image_paths = []
    updated_scenes = []

    for i, scene in enumerate(scenes):
        scene_num = scene.get("scene_number", i + 1)
        update_scene_status(visual_status, scene_num, "generating")

        if status_callback:
            status_callback(visual_status)

        topic = scene.get("topic") or (db_session.query(video_model).filter(video_model.id == video_id).first().prompt if video_model else "") or ""
        claim = scene.get("claim") or ""
        narration = scene.get("narration") or ""
        v_prompt = scene.get("visual_prompt") or scene.get("visual_description", "")
        style = scene.get("visual_style") or visual_style

        # Semantic validation & repair before image generation
        is_valid, reason = validate_visual_prompt_grounding(
            topic=topic,
            claim=claim,
            narration=narration,
            visual_prompt=v_prompt,
        )
        if not is_valid:
            v_prompt = regenerate_grounded_visual_prompt(
                topic=topic,
                claim=claim,
                narration=narration,
                visual_style=style,
            )
            print(f"[Semantic Validation] Scene {scene_num}: Auto-repairing ungrounded prompt -> {v_prompt}")

        # Upsert SceneAsset record
        asset = (
            db_session.query(scene_asset_model)
            .filter(
                scene_asset_model.video_id == video_id,
                scene_asset_model.scene_number == scene_num,
            )
            .first()
        )
        if not asset:
            asset = scene_asset_model(
                video_id=video_id,
                scene_number=scene_num,
                status="generating",
            )
            db_session.add(asset)

        asset.status = "generating"
        asset.visual_prompt = v_prompt
        asset.updated_at = datetime.utcnow()
        db_session.commit()

        output_path = scene_image_path(base_dir, scene_num)
        consistency = build_consistency_context(scenes, scene_num)

        # Parse duration for scene motion video
        dur_val = scene.get("duration") or 5
        try:
            dur_float = float(dur_val)
        except Exception:
            dur_float = 5.0

        request = VisualGenerationRequest(
            scene_number=scene_num,
            visual_prompt=v_prompt,
            environment=scene.get("environment", ""),
            characters=scene.get("characters", ""),
            objects=scene.get("objects", ""),
            camera_style=scene.get("camera_style", ""),
            visual_style=style,
            consistency_context=consistency,
            width=width,
            height=height,
            output_path=output_path,
            topic=topic,
            claim=claim,
            narration=narration,
            duration=dur_float,
            stock_query=scene.get("stock_query", ""),
            video_motion_prompt=scene.get("video_motion_prompt", ""),
            media_type="auto",
        )

        result = service.generate_scene(request)

        scene_copy = dict(scene)
        scene_copy["visual_prompt"] = v_prompt
        scene_copy["visual_description"] = v_prompt
        if result.success:
            actual_path = result.output_path
            is_video = actual_path.lower().endswith((".mp4", ".mov", ".webm")) or result.media_type == "video"
            ext = os.path.splitext(actual_path)[1]

            scene_copy["image_path"] = actual_path
            scene_copy["media_path"] = actual_path
            scene_copy["media_type"] = "video" if is_video else "image"
            if is_video:
                scene_copy["video_path"] = actual_path
                scene_copy["video_url"] = f"/assets/video_{video_id}/scene_{scene_num:03d}{ext}"
                scene_copy["image_url"] = scene_copy["video_url"]
            else:
                scene_copy["image_url"] = scene_image_url(video_id, scene_num)
                if result.metadata.get("video_clip_path"):
                    scene_copy["video_path"] = result.metadata["video_clip_path"]

            scene_copy["visual_status"] = "completed"
            scene_copy["is_mock_visual"] = result.is_mock
            image_paths.append(actual_path)

            asset.status = "completed"
            asset.image_path = actual_path
            asset.provider = result.provider_name
            asset.is_mock = result.is_mock
            asset.metadata_json = result.metadata
            asset.error_message = None
            update_scene_status(visual_status, scene_num, "completed")
        else:
            scene_copy["visual_status"] = "failed"
            asset.status = "failed"
            asset.error_message = result.error_message
            update_scene_status(visual_status, scene_num, "failed")
            raise RuntimeError(
                f"Visual generation failed for scene {scene_num}: {result.error_message}"
            )

        updated_scenes.append(scene_copy)
        db_session.commit()

        if status_callback:
            status_callback(visual_status)

    visual_status["fallback_used"] = service.fallback_used
    visual_status["fallback_reason"] = service.fallback_reason
    visual_status["updated_at"] = datetime.utcnow().isoformat()

    return image_paths, updated_scenes, visual_status


def regenerate_single_scene(
    video_id: int,
    scene_number: int,
    scene: dict,
    all_scenes: list,
    base_dir: str,
    visual_style: str,
    db_session,
    scene_asset_model,
    width: int = 1080,
    height: int = 1920,
) -> dict:
    """Regenerate visual for a single scene."""
    service = VisualGenerationService()
    output_path = scene_image_path(base_dir, scene_number)
    consistency = build_consistency_context(all_scenes, scene_number)
    style = scene.get("visual_style") or visual_style

    topic = scene.get("topic") or ""
    claim = scene.get("claim") or ""
    narration = scene.get("narration") or ""
    v_prompt = scene.get("visual_prompt") or scene.get("visual_description", "")

    is_valid, reason = validate_visual_prompt_grounding(
        topic=topic,
        claim=claim,
        narration=narration,
        visual_prompt=v_prompt,
    )
    if not is_valid:
        v_prompt = regenerate_grounded_visual_prompt(
            topic=topic,
            claim=claim,
            narration=narration,
            visual_style=style,
        )

    asset = (
        db_session.query(scene_asset_model)
        .filter(
            scene_asset_model.video_id == video_id,
            scene_asset_model.scene_number == scene_number,
        )
        .first()
    )
    if not asset:
        asset = scene_asset_model(
            video_id=video_id,
            scene_number=scene_number,
            status="generating",
        )
        db_session.add(asset)

    asset.status = "generating"
    asset.visual_prompt = v_prompt
    asset.updated_at = datetime.utcnow()
    db_session.commit()

    request = VisualGenerationRequest(
        scene_number=scene_number,
        visual_prompt=v_prompt,
        environment=scene.get("environment", ""),
        characters=scene.get("characters", ""),
        objects=scene.get("objects", ""),
        camera_style=scene.get("camera_style", ""),
        visual_style=style,
        consistency_context=consistency,
        width=width,
        height=height,
        output_path=output_path,
        topic=topic,
        claim=claim,
        duration=float(scene.get("duration") or 5.0),
        stock_query=scene.get("stock_query", ""),
        video_motion_prompt=scene.get("video_motion_prompt", ""),
        media_type="auto",
    )

    result = service.generate_scene(request)
    if not result.success:
        asset.status = "failed"
        asset.error_message = result.error_message
        db_session.commit()
        raise RuntimeError(result.error_message)

    actual_path = result.output_path
    is_video = actual_path.lower().endswith((".mp4", ".mov", ".webm")) or result.media_type == "video"
    ext = os.path.splitext(actual_path)[1]

    asset.status = "completed"
    asset.image_path = actual_path
    asset.provider = result.provider_name
    asset.is_mock = result.is_mock
    asset.metadata_json = result.metadata
    asset.error_message = None
    db_session.commit()

    updated = dict(scene)
    updated["image_path"] = actual_path
    updated["media_path"] = actual_path
    updated["media_type"] = "video" if is_video else "image"
    if is_video:
        updated["video_path"] = actual_path
        updated["video_url"] = f"/assets/video_{video_id}/scene_{scene_number:03d}{ext}"
        updated["image_url"] = updated["video_url"]
    else:
        updated["image_url"] = scene_image_url(video_id, scene_number)
        if result.metadata.get("video_clip_path"):
            updated["video_path"] = result.metadata["video_clip_path"]
    updated["visual_status"] = "completed"
    updated["is_mock_visual"] = result.is_mock
    return updated
