from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Header, Query, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import os
import json
import time
import secrets
from datetime import datetime, timedelta

from . import models, schemas, database
from services.llm.agent import generate_video_plan
from services.tts.generator import generate_voiceover
from services.subtitles.transcriber import generate_subtitles
from services.video_processing.composer import compose_video
from services.visual_generation import VisualGenerationService, get_visual_provider
from services.visual_generation.base import validate_generated_image, validate_generated_media
from services.visual_generation.pipeline_helpers import (
    generate_scene_visuals,
    regenerate_single_scene,
    init_visual_status,
    update_scene_status,
    scene_image_path,
)
from social import SocialProviderRegistry, encrypt_token, decrypt_token

# Ensure tables are created and migrated
models.Base.metadata.create_all(bind=database.engine)


def _migrate_schema():
    """Add new columns to existing SQLite databases."""
    from sqlalchemy import inspect, text
    inspector = inspect(database.engine)
    if "videos" not in inspector.get_table_names():
        return

    # Migrate videos table
    existing = {c["name"] for c in inspector.get_columns("videos")}
    video_migrations = [
        ("visual_style", "VARCHAR DEFAULT 'realistic'"),
        ("visual_provider", "VARCHAR"),
        ("visual_generation_status", "JSON"),
        ("selected_platforms", "JSON"),
    ]
    with database.engine.begin() as conn:
        for col, typedef in video_migrations:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE videos ADD COLUMN {col} {typedef}"))

    # Create video_publications table if it doesn't exist
    if "video_publications" not in inspector.get_table_names():
        with database.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS video_publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL REFERENCES videos(id),
                    platform VARCHAR NOT NULL,
                    social_account_id INTEGER REFERENCES social_accounts(id),
                    status VARCHAR NOT NULL DEFAULT 'QUEUED',
                    platform_post_id VARCHAR,
                    post_url VARCHAR,
                    error_message TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    published_at DATETIME,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))


_migrate_schema()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Video Automation API - Phase 5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve assets folder
os.makedirs("assets", exist_ok=True)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


def verify_admin_auth(x_admin_role: Optional[str] = Header(default="admin")):
    """
    Authorization dependency: verifies the requester is an authorized admin.
    Defaults to 'admin' for easy local testing, but rejects non-admin roles.
    """
    if x_admin_role and x_admin_role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized: Admin privileges required")
    return True


@app.get("/")
def read_root():
    return {"message": "AI Video Automation API with Phase 4 Admin Review is running"}


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is running smoothly!"}


# ---------------------------------------------------------------------- #
# Video Creation & Plan Generation (Initial state: DRAFT)
# ---------------------------------------------------------------------- #
@app.post("/videos/", response_model=schemas.VideoResponse)
def create_video(video: schemas.VideoCreate, db: Session = Depends(database.get_db)):
    prompt_text = (video.prompt or video.topic or "").strip()
    if not prompt_text:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "topic"], "msg": "Topic is required", "type": "missing"}]
        )

    # 1. Create initial draft video record
    try:
        visual_style = (video.visual_style or "realistic").lower()
        resolution = "1920x1080" if video.aspect_ratio == "16:9" else "1080x1920"
        db_video = models.Video(
            prompt=prompt_text,
            duration=video.duration or "30-60 seconds",
            language=video.language or "English",
            style=video.style or video.tone or "Standard",
            target_platform=video.target_platform or (video.selected_platforms[0] if video.selected_platforms else "TikTok"),
            visual_style=visual_style,
            visual_provider=video.visual_provider,
            selected_platforms=video.selected_platforms,
            owner_id=1,
            status=models.VideoStatus.DRAFT,
            generation_stage="NOT_STARTED",
            resolution=resolution
        )
        db.add(db_video)
        db.commit()
        db.refresh(db_video)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during video creation: {str(e)}")

    # 2. Call LLM Service to create initial plan & script
    try:
        plan = generate_video_plan(
            prompt=prompt_text,
            duration=video.duration or "30-60 seconds",
            language=video.language or "English",
            style=video.style or video.tone or "Standard",
            target_platform=video.target_platform or (video.selected_platforms[0] if video.selected_platforms else "TikTok"),
            visual_style=visual_style,
        )

        plan_dict = plan.model_dump()
        db_video.plan = plan_dict
        db_video.original_plan = plan_dict  # Preserve pristine original
        db_video.title = plan.title
        db_video.script = plan.complete_narration
        db_video.caption = plan.caption
        db_video.hashtags = plan.hashtags
        db_video.status = models.VideoStatus.DRAFT
        db.commit()
        db.refresh(db_video)

    except Exception as e:
        db_video.status = models.VideoStatus.FAILED
        db_video.error_message = f"LLM Generation failed: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    return db_video


# ---------------------------------------------------------------------- #
# QA & Validation Engine
# ---------------------------------------------------------------------- #
def run_qa_validation(video_id: int, db: Session) -> bool:
    """
    Validates generated video:
    - Checks file presence and size
    - Reads playable duration and resolution
    - Validates presence of title, narration, scenes
    Updates video status to PENDING_APPROVAL on pass or FAILED on error.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        return False

    video.status = models.VideoStatus.QA_PENDING
    db.commit()

    qa_report = {
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
        "passed": False
    }

    # Check 1: Video file on disk
    video_path = video.video_path
    if not video_path or not os.path.exists(video_path):
        qa_report["checks"]["file_exists"] = False
        qa_report["error"] = "Video file does not exist on disk"
        video.qa_report = qa_report
        video.status = models.VideoStatus.FAILED
        video.error_message = qa_report["error"]
        db.commit()
        return False

    file_size = os.path.getsize(video_path)
    qa_report["checks"]["file_exists"] = True
    qa_report["checks"]["file_size_bytes"] = file_size

    if file_size < 1000:
        qa_report["checks"]["file_size_valid"] = False
        qa_report["error"] = "Video file is corrupted or empty"
        video.qa_report = qa_report
        video.status = models.VideoStatus.FAILED
        video.error_message = qa_report["error"]
        db.commit()
        return False
    qa_report["checks"]["file_size_valid"] = True

    # Check 2: Playability & Duration
    try:
        try:
            from moviepy import VideoFileClip
        except ImportError:
            from moviepy.editor import VideoFileClip
        clip = VideoFileClip(video_path)
        duration = clip.duration
        resolution = f"{clip.size[0]}x{clip.size[1]}"
        has_audio = clip.audio is not None
        clip.close()

        qa_report["checks"]["playable"] = True
        qa_report["checks"]["duration_seconds"] = round(duration, 2)
        qa_report["checks"]["resolution"] = resolution
        qa_report["checks"]["has_audio"] = has_audio
    except Exception as e:
        qa_report["checks"]["playable"] = False
        qa_report["error"] = f"Video playback check failed: {str(e)}"
        video.qa_report = qa_report
        video.status = models.VideoStatus.FAILED
        video.error_message = qa_report["error"]
        db.commit()
        return False

    # Check 3: Metadata completeness
    plan = video.plan or {}
    has_title = bool(video.title or plan.get("title"))
    has_script = bool(video.script or plan.get("complete_narration"))
    has_scenes = bool(plan.get("scenes"))
    scenes = plan.get("scenes", [])
    scene_images_ok = all(
        (s.get("image_path") or s.get("video_path")) and validate_generated_media(s.get("image_path") or s.get("video_path", ""))[0]
        for s in scenes
    ) if scenes else False

    qa_report["checks"]["has_title"] = has_title
    qa_report["checks"]["has_script"] = has_script
    qa_report["checks"]["has_scenes"] = has_scenes
    qa_report["checks"]["scene_images_generated"] = scene_images_ok

    if not (has_title and has_script and has_scenes):
        qa_report["error"] = "Video metadata incomplete (missing title, script, or scenes)"
        video.qa_report = qa_report
        video.status = models.VideoStatus.FAILED
        video.error_message = qa_report["error"]
        db.commit()
        return False

    if scenes and not scene_images_ok:
        qa_report["error"] = "One or more scene visual images are missing"
        video.qa_report = qa_report
        video.status = models.VideoStatus.FAILED
        video.error_message = qa_report["error"]
        db.commit()
        return False

    # Passed QA -> Transition to PENDING_APPROVAL
    qa_report["passed"] = True
    qa_report["summary"] = f"Passed QA: {resolution}, {round(duration, 1)}s, audio OK"
    video.qa_report = qa_report
    video.status = models.VideoStatus.PENDING_APPROVAL
    video.generation_stage = "DONE"
    video.error_message = None
    video.updated_at = datetime.utcnow()
    db.commit()
    return True


# ---------------------------------------------------------------------- #
# Background Pipeline Execution
# ---------------------------------------------------------------------- #
def _parse_resolution(resolution: str) -> tuple[int, int]:
    try:
        w, h = resolution.lower().split("x")
        return int(w), int(h)
    except Exception:
        return 1080, 1920


def _get_scene_durations(scenes: list) -> list:
    """Extract duration per scene from structured or legacy fields."""
    durations = []
    for scene in scenes:
        if scene.get("duration"):
            durations.append(scene["duration"])
        elif scene.get("scene_duration"):
            durations.append(scene["scene_duration"])
        else:
            durations.append(5)
    return durations


def run_video_pipeline(video_id: int):
    """
    Full visual video pipeline:
    Script/Plan (already done) -> Visual Prompts (in plan) ->
    AI Image Generation -> Voiceover -> Subtitles -> FFmpeg Composition (with animation)
    """
    db = database.SessionLocal()
    try:
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video or not video.plan:
            return

        attempt_count = db.query(models.GenerationAttempt).filter(
            models.GenerationAttempt.video_id == video_id
        ).count() + 1
        attempt = models.GenerationAttempt(
            video_id=video_id,
            attempt_number=attempt_count,
            stage="VISUALS",
            status="STARTED",
            started_at=datetime.utcnow()
        )
        db.add(attempt)

        video.status = models.VideoStatus.GENERATING
        video.error_message = None
        video.updated_at = datetime.utcnow()
        db.commit()

        plan = dict(video.plan)
        base_dir = f"assets/video_{video_id}"
        os.makedirs(base_dir, exist_ok=True)
        width, height = _parse_resolution(video.resolution or "1080x1920")
        visual_style = video.visual_style or "realistic"
        scenes = plan.get("scenes", [])
        topic_name = plan.get("topic") or video.prompt or ""
        for s in scenes:
            if not s.get("topic"):
                s["topic"] = topic_name

        def _persist_visual_status(status: dict):
            video.visual_generation_status = status
            db.commit()

        try:
            # 1. AI Image Generation for each scene
            video.generation_stage = "VISUALS"
            attempt.stage = "VISUALS"
            video.visual_generation_status = init_visual_status(scenes)
            db.commit()

            image_paths, updated_scenes, visual_status = generate_scene_visuals(
                video_id=video_id,
                scenes=scenes,
                base_dir=base_dir,
                visual_style=visual_style,
                db_session=db,
                video_model=models.Video,
                scene_asset_model=models.SceneAsset,
                width=width,
                height=height,
                status_callback=_persist_visual_status,
                visual_provider=video.visual_provider,
            )

            plan["scenes"] = updated_scenes
            video.plan = plan
            video.visual_generation_status = visual_status
            video.visual_provider = visual_status.get("provider")
            db.commit()

            if visual_status.get("fallback_used"):
                print(
                    f"[VisualGen] Warning: fallback to mock provider used. "
                    f"Reason: {visual_status.get('fallback_reason')}"
                )

            # 2. Voiceover
            video.generation_stage = "VOICEOVER"
            attempt.stage = "VOICEOVER"
            db.commit()
            audio_path = os.path.join(base_dir, "voiceover.mp3")
            narration = video.script or plan.get("complete_narration", "")
            generate_voiceover(narration, audio_path)
            video.audio_path = audio_path
            db.commit()

            # 3. Subtitles
            video.generation_stage = "SUBTITLES"
            attempt.stage = "SUBTITLES"
            db.commit()
            srt_path = generate_subtitles(audio_path, base_dir, "voiceover", fallback_text=narration, width=width, height=height)
            video.subtitles_path = srt_path
            db.commit()

            # 4. Compose with scene animation + subtitle overlay
            video.generation_stage = "COMPOSING"
            attempt.stage = "COMPOSING"
            db.commit()

            durations = _get_scene_durations(updated_scenes)
            if audio_path and os.path.exists(audio_path):
                try:
                    try:
                        from moviepy import AudioFileClip
                    except ImportError:
                        from moviepy.editor import AudioFileClip
                    a_clip = AudioFileClip(audio_path)
                    a_dur = a_clip.duration
                    a_clip.close()
                    if a_dur and len(durations) > 0:
                        per_scene = round(a_dur / len(durations), 2)
                        durations = [per_scene] * len(durations)
                        durations[-1] = round(a_dur - sum(durations[:-1]), 2)
                except Exception:
                    pass
            final_mp4 = os.path.join(base_dir, "final.mp4")
            compose_video(image_paths, durations, audio_path, srt_path, final_mp4, width, height)
            video.video_path = final_mp4
            video.video_url = f"/assets/video_{video_id}/final.mp4"
            video.status = models.VideoStatus.GENERATED
            db.commit()

            attempt.status = "COMPLETED"
            attempt.completed_at = datetime.utcnow()
            db.commit()

            # 5. QA -> PENDING_APPROVAL
            run_qa_validation(video_id, db)

        except Exception as e:
            import traceback
            traceback.print_exc()
            video.status = models.VideoStatus.FAILED
            video.error_message = str(e)
            attempt.status = "FAILED"
            attempt.error_message = str(e)
            attempt.completed_at = datetime.utcnow()
            db.commit()

    finally:
        db.close()


@app.post("/videos/{video_id}/generate")
def start_generation(
    video_id: int,
    background_tasks: BackgroundTasks,
    options: Optional[schemas.VideoGenerateOptions] = None,
    db: Session = Depends(database.get_db)
):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if options:
        if options.visual_provider:
            video.visual_provider = options.visual_provider
        if options.visual_style:
            video.visual_style = options.visual_style.lower()
        if options.selected_platforms:
            video.selected_platforms = options.selected_platforms

    video.status = models.VideoStatus.GENERATING
    db.commit()
    background_tasks.add_task(run_video_pipeline, video_id)
    return {"status": "started", "video_id": video_id}


# ---------------------------------------------------------------------- #
# Phase 4: Admin Review & Approval Endpoints
# ---------------------------------------------------------------------- #
@app.post("/videos/{video_id}/approve", response_model=schemas.VideoResponse)
def approve_video(
    video_id: int,
    db: Session = Depends(database.get_db),
    authorized: bool = Depends(verify_admin_auth)
):
    """
    Admin APPROVE action:
    - Validates that the video file exists and is playable.
    - Validates that required metadata exists.
    - Transitions status to APPROVED.
    - Does NOT publish anything yet.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 1. Validation: video exists on disk
    if not video.video_path or not os.path.exists(video.video_path):
        raise HTTPException(status_code=400, detail="Cannot approve: Video file does not exist on disk.")

    if os.path.getsize(video.video_path) < 1000:
        raise HTTPException(status_code=400, detail="Cannot approve: Video file is empty or corrupted.")

    # 2. Validation: required metadata exists
    plan = video.plan or {}
    if not (video.title or plan.get("title")):
        raise HTTPException(status_code=400, detail="Cannot approve: Title metadata is missing.")
    if not (video.script or plan.get("complete_narration")):
        raise HTTPException(status_code=400, detail="Cannot approve: Script metadata is missing.")

    # 3. Record Approval
    approval = models.Approval(
        video_id=video.id,
        reviewer_id=1,
        action="APPROVED",
        is_approved=True,
        comments="Approved by admin review",
        reviewed_at=datetime.utcnow()
    )
    db.add(approval)

    # 4. Update status
    video.status = models.VideoStatus.APPROVED
    video.rejection_reason = None
    video.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(video)

    return video


# ---------------------------------------------------------------------- #
# Phase 5: Approve & Publish — Explicit user action
# ---------------------------------------------------------------------- #
def is_tiktok_sandbox_or_unaudited() -> bool:
    """
    Returns True if the TikTok integration is operating in Sandbox, Development, or unaudited mode.
    """
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    if client_key.startswith("sb"):
        return True
    if os.getenv("TIKTOK_IS_SANDBOX", "false").lower() in ("true", "1", "yes"):
        return True
    if os.getenv("TIKTOK_UNAUDITED", "false").lower() in ("true", "1", "yes"):
        return True
    return False


def _do_publish_platform(
    platform: str,
    video: "models.Video",
    pub_record: "models.VideoPublication",
    db: Session,
    use_sandbox: bool = False,
    youtube_privacy: str = "public",
    tiktok_privacy: str = "PUBLIC_TO_EVERYONE",
):
    """
    Internal helper: publishes a single platform using the appropriate provider.
    Updates pub_record in-place. Never surfaces raw tokens in errors or logs.
    """
    pub_record.status = models.PublicationStatus.PUBLISHING
    pub_record.attempt_count = (pub_record.attempt_count or 0) + 1
    db.commit()

    video_path = video.video_path
    if not video_path or not os.path.exists(video_path):
        pub_record.status = models.PublicationStatus.FAILED
        pub_record.error_message = "Video file not found on disk."
        pub_record.updated_at = datetime.utcnow()
        db.commit()
        return

    account = db.query(models.SocialAccount).filter(
        models.SocialAccount.id == pub_record.social_account_id
    ).first()

    if not account or not account.encrypted_access_token:
        pub_record.status = models.PublicationStatus.FAILED
        pub_record.error_message = f"No active {platform} account connected. Please connect an account first."
        pub_record.updated_at = datetime.utcnow()
        db.commit()
        return

    if account.status != "ACTIVE":
        pub_record.status = models.PublicationStatus.FAILED
        pub_record.error_message = f"{platform} account '{account.account_name}' status is {account.status}. Please reconnect."
        pub_record.updated_at = datetime.utcnow()
        db.commit()
        return

    effective_sandbox = use_sandbox or (account is not None and getattr(account, "is_mock", False))

    # Proactive token expiration check & refresh before calling provider (only for real accounts)
    if account.encrypted_refresh_token and not effective_sandbox and not account.is_mock:
        now = datetime.utcnow()
        needs_refresh = False
        if account.token_expires_at:
            # Expired or expiring within 5 minutes (300s)
            needs_refresh = account.token_expires_at <= (now + timedelta(minutes=5))
        elif platform == "youtube" and not account.is_mock:
            # If no expiration timestamp exists on a real account, refresh proactively
            needs_refresh = True

        if needs_refresh:
            try:
                refresh_tok = decrypt_token(account.encrypted_refresh_token)
                prov = SocialProviderRegistry.get_provider(platform, use_sandbox=False)
                refreshed = prov.refresh_access_token(refresh_tok)
                if refreshed and refreshed.get("access_token"):
                    account.encrypted_access_token = encrypt_token(refreshed["access_token"])
                    if refreshed.get("refresh_token"):
                        account.encrypted_refresh_token = encrypt_token(refreshed["refresh_token"])
                    if refreshed.get("expires_in"):
                        account.token_expires_at = datetime.utcnow() + timedelta(seconds=int(refreshed["expires_in"]))
                    account.status = "ACTIVE"
                    account.updated_at = datetime.utcnow()
                    db.commit()
                    db.refresh(account)
            except Exception:
                # If proactive refresh fails, attempt with current token or reactive handler
                pass

    try:
        access_token = decrypt_token(account.encrypted_access_token)
    except Exception:
        pub_record.status = models.PublicationStatus.FAILED
        pub_record.error_message = f"Failed to read stored {platform} credentials. Please reconnect the account."
        pub_record.updated_at = datetime.utcnow()
        db.commit()
        return

    plan = video.plan or {}
    base_title = (video.title or plan.get("title") or f"Video #{video.id}")[:100]
    base_caption = video.caption or plan.get("caption") or ""
    base_narration = video.script or plan.get("complete_narration") or ""
    base_tags = video.hashtags or plan.get("hashtags") or []
    tags_list = base_tags if isinstance(base_tags, list) else []

    if platform == "youtube":
        tags_clean = [t.lstrip("#") for t in tags_list]
        desc = f"{base_caption}\n\n{' '.join(tags_list)}\n\n{base_narration}".strip()[:5000]
        metadata = {"title": base_title, "description": desc, "privacy": youtube_privacy, "tags": tags_clean}
    elif platform == "instagram":
        hashtag_str = " ".join(tags_list)
        caption = f"{base_caption}\n\n{hashtag_str}".strip()[:2200]
        metadata = {"caption": caption, "hashtags": tags_list, "share_to_feed": True, "account_id": account.account_id}
    elif platform == "tiktok":
        hashtag_str = " ".join(tags_list)
        tt_caption = f"{base_caption} {hashtag_str}".strip()[:2200]
        # Enforce SELF_ONLY if in sandbox / unaudited mode
        effective_privacy = "SELF_ONLY" if is_tiktok_sandbox_or_unaudited() else tiktok_privacy
        metadata = {
            "caption": tt_caption,
            "privacy": effective_privacy,
            "allow_comments": True,
            "allow_duet": True,
            "allow_stitch": True,
            "account_handle": account.account_handle,
            "publish_id": pub_record.platform_post_id
        }
    else:
        pub_record.status = models.PublicationStatus.FAILED
        pub_record.error_message = f"Unknown platform: {platform}"
        pub_record.updated_at = datetime.utcnow()
        db.commit()
        return

    try:
        provider = SocialProviderRegistry.get_provider(platform, use_sandbox=effective_sandbox)
        result = provider.publish_video(access_token=access_token, video_path=video_path, metadata=metadata)

        # Reactive refresh: handle 401 / stale token case safely if initial call failed
        if not result.get("success") and account.encrypted_refresh_token and not effective_sandbox:
            err_msg = (result.get("error") or "").lower()
            if "401" in err_msg or "invalid authentication" in err_msg or "unauthorized" in err_msg:
                try:
                    refresh_tok = decrypt_token(account.encrypted_refresh_token)
                    refreshed = provider.refresh_access_token(refresh_tok)
                    if refreshed and refreshed.get("access_token"):
                        account.encrypted_access_token = encrypt_token(refreshed["access_token"])
                        if refreshed.get("refresh_token"):
                            account.encrypted_refresh_token = encrypt_token(refreshed["refresh_token"])
                        if refreshed.get("expires_in"):
                            account.token_expires_at = datetime.utcnow() + timedelta(seconds=int(refreshed["expires_in"]))
                        account.status = "ACTIVE"
                        account.updated_at = datetime.utcnow()
                        db.commit()
                        db.refresh(account)
                        new_access_token = refreshed["access_token"]
                        # Retry publishing once with refreshed token
                        result = provider.publish_video(access_token=new_access_token, video_path=video_path, metadata=metadata)
                except Exception:
                    pass

        if result.get("success"):
            pub_record.status = models.PublicationStatus.PUBLISHED
            pub_record.platform_post_id = result.get("external_post_id") or result.get("publish_id")
            pub_record.post_url = result.get("post_url")
            pub_record.error_message = None
            pub_record.published_at = datetime.utcnow()
        else:
            pub_record.status = models.PublicationStatus.FAILED
            raw_err = result.get("error") or "Unknown publishing error."
            pub_record.error_message = raw_err[:1000]
            if result.get("publish_id"):
                pub_record.platform_post_id = result.get("publish_id")
    except Exception as exc:
        pub_record.status = models.PublicationStatus.FAILED
        pub_record.error_message = f"Publishing exception: {str(exc)[:500]}"

    pub_record.updated_at = datetime.utcnow()
    db.commit()


@app.post("/videos/{video_id}/approve-and-publish", response_model=schemas.ApproveAndPublishResponse)
def approve_and_publish_video(
    video_id: int,
    payload: schemas.ApproveAndPublishRequest,
    db: Session = Depends(database.get_db),
    authorized: bool = Depends(verify_admin_auth)
):
    """
    Phase 5 Approve & Publish:
    1. Validates the video (same checks as /approve).
    2. Records approval in the approvals table.
    3. Transitions video to APPROVED.
    4. For each selected platform, finds the connected account and creates a VideoPublication record.
    5. Publishes to each platform independently — one failure does NOT block others.
    6. Returns per-platform status (PUBLISHED, FAILED, NOT_SELECTED).

    RULES:
    - Never publishes before approval.
    - Never publishes to a platform that was not selected.
    - use_sandbox=true uses the mock provider for safe zero-credential testing.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status not in [models.VideoStatus.PENDING_APPROVAL]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve: video is in '{video.status}' status. Must be PENDING_APPROVAL."
        )

    if not video.video_path or not os.path.exists(video.video_path):
        raise HTTPException(status_code=400, detail="Cannot approve: Video file does not exist on disk.")
    if os.path.getsize(video.video_path) < 1000:
        raise HTTPException(status_code=400, detail="Cannot approve: Video file is empty or corrupted.")

    plan = video.plan or {}
    if not (video.title or plan.get("title")):
        raise HTTPException(status_code=400, detail="Cannot approve: Title metadata is missing.")
    if not (video.script or plan.get("complete_narration")):
        raise HTTPException(status_code=400, detail="Cannot approve: Script metadata is missing.")

    selected = [p.lower().strip() for p in payload.selected_platforms if p.strip()]
    supported = ["youtube", "instagram", "tiktok"]
    invalid = [p for p in selected if p not in supported]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported platforms: {invalid}. Must be one of {supported}.")
    if not selected:
        raise HTTPException(status_code=400, detail="At least one platform must be selected.")

    # === Step 1: Record approval ===
    approval = models.Approval(
        video_id=video.id,
        reviewer_id=1,
        action="APPROVED",
        is_approved=True,
        comments=f"Approved & publishing to: {', '.join(selected)}",
        reviewed_at=datetime.utcnow()
    )
    db.add(approval)
    video.status = models.VideoStatus.APPROVED
    video.selected_platforms = selected
    video.rejection_reason = None
    video.updated_at = datetime.utcnow()
    db.commit()

    # === Step 2: Create VideoPublication records ===
    pub_records: List[models.VideoPublication] = []
    all_platforms = ["youtube", "instagram", "tiktok"]

    for platform in all_platforms:
        if platform not in selected:
            pub = models.VideoPublication(
                video_id=video.id, platform=platform,
                social_account_id=None, status=models.PublicationStatus.NOT_SELECTED, attempt_count=0,
            )
            db.add(pub)
            pub_records.append(pub)
        else:
            # Find connected account: prefer real account, fall back to sandbox
            acct_q = db.query(models.SocialAccount).filter(
                models.SocialAccount.platform == platform,
                models.SocialAccount.status == "ACTIVE"
            )
            if payload.use_sandbox:
                connected_account = acct_q.filter(models.SocialAccount.is_mock == True).first()
            else:
                connected_account = acct_q.filter(models.SocialAccount.is_mock == False).first()
                if not connected_account:
                    connected_account = acct_q.filter(models.SocialAccount.is_mock == True).first()

            if not connected_account:
                # Auto-provision sandbox account so publishing can proceed smoothly
                mock_p = SocialProviderRegistry.get_provider(platform, use_sandbox=True)
                tks = mock_p.exchange_code_for_tokens("auto_code", "http://localhost")
                info = mock_p.get_account_info(tks["access_token"])
                connected_account = models.SocialAccount(
                    user_id=1,
                    platform=platform,
                    account_id=info.get("account_id"),
                    account_name=info.get("account_name"),
                    account_handle=info.get("account_handle"),
                    encrypted_access_token=encrypt_token(tks["access_token"]),
                    encrypted_refresh_token=encrypt_token(tks.get("refresh_token")),
                    status="ACTIVE",
                    is_mock=True,
                    metadata_json={"avatar_url": info.get("avatar_url"), "profile_url": info.get("profile_url")}
                )
                db.add(connected_account)
                db.commit()
                db.refresh(connected_account)

            pub = models.VideoPublication(
                video_id=video.id, platform=platform,
                social_account_id=connected_account.id,
                status=models.PublicationStatus.QUEUED, attempt_count=0,
            )
            db.add(pub)
            pub_records.append(pub)

    db.commit()
    for pub in pub_records:
        db.refresh(pub)

    # === Step 3: Publish to each QUEUED platform independently ===
    for pub in pub_records:
        if pub.status == models.PublicationStatus.QUEUED:
            _do_publish_platform(
                platform=pub.platform, video=video, pub_record=pub, db=db,
                use_sandbox=payload.use_sandbox,
                youtube_privacy=payload.youtube_privacy,
                tiktok_privacy=payload.tiktok_privacy,
            )

    # === Step 4: Build summary & update video status ===
    db.refresh(video)
    for pub in pub_records:
        db.refresh(pub)

    summary = {pub.platform: pub.status.value for pub in pub_records}
    published_count = sum(1 for pub in pub_records if pub.status == models.PublicationStatus.PUBLISHED)
    if published_count > 0:
        video.status = models.VideoStatus.PUBLISHED
        video.updated_at = datetime.utcnow()
        db.commit()

    pub_summaries = [p for p in selected if summary.get(p) == "PUBLISHED"]
    fail_summaries = [p for p in selected if summary.get(p) == "FAILED"]
    msg_parts = []
    if pub_summaries:
        msg_parts.append(f"Published to: {', '.join(pub_summaries)}")
    if fail_summaries:
        msg_parts.append(f"Failed on: {', '.join(fail_summaries)}")
    message = " | ".join(msg_parts) or "No platforms were published."

    return schemas.ApproveAndPublishResponse(
        video_id=video.id,
        video_status=video.status.value,
        selected_platforms=selected,
        publications=[schemas.VideoPublicationResponse.model_validate(p) for p in pub_records],
        summary=summary,
        message=message,
    )


@app.get("/publications", response_model=List[schemas.VideoPublicationResponse])
def get_all_publications(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    """Returns all publication records across all videos, optionally filtered by platform or status."""
    q = db.query(models.VideoPublication)
    if platform:
        q = q.filter(models.VideoPublication.platform == platform.lower().strip())
    if status:
        q = q.filter(models.VideoPublication.status == status.upper().strip())
    return q.order_by(models.VideoPublication.updated_at.desc()).all()


@app.get("/videos/{video_id}/publications", response_model=List[schemas.VideoPublicationResponse])
def get_video_publications(
    video_id: int,
    db: Session = Depends(database.get_db)
):
    """Returns per-platform publication records for a video (PUBLISHED, FAILED, NOT_SELECTED)."""
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    pubs = db.query(models.VideoPublication).filter(
        models.VideoPublication.video_id == video_id
    ).order_by(models.VideoPublication.id.asc()).all()
    return pubs


@app.post("/videos/{video_id}/publications/{platform}/retry", response_model=schemas.VideoPublicationResponse)
def retry_platform_publication(
    video_id: int,
    platform: str,
    db: Session = Depends(database.get_db),
    authorized: bool = Depends(verify_admin_auth),
    use_sandbox: bool = False,
):
    """
    Retry publishing to a single FAILED platform.
    - Does NOT regenerate the video.
    - Does NOT republish PUBLISHED platforms.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    pub = db.query(models.VideoPublication).filter(
        models.VideoPublication.video_id == video_id,
        models.VideoPublication.platform == platform.lower().strip()
    ).order_by(models.VideoPublication.id.desc()).first()

    if not pub:
        raise HTTPException(status_code=404, detail=f"No publication record for platform '{platform}' on video #{video_id}.")
    if pub.status == models.PublicationStatus.NOT_SELECTED:
        raise HTTPException(status_code=400, detail=f"Platform '{platform}' was not selected for this video.")
    if pub.status == models.PublicationStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail=f"Platform '{platform}' is already PUBLISHED.")

    if not pub.social_account_id:
        acct = db.query(models.SocialAccount).filter(
            models.SocialAccount.platform == platform.lower(),
            models.SocialAccount.status == "ACTIVE"
        ).first()
        if acct:
            pub.social_account_id = acct.id
            db.commit()

    _do_publish_platform(platform=pub.platform, video=video, pub_record=pub, db=db, use_sandbox=use_sandbox)
    db.refresh(pub)
    if pub.status == models.PublicationStatus.PUBLISHED:
        video.status = models.VideoStatus.PUBLISHED
        video.updated_at = datetime.utcnow()
        db.commit()
    return pub


@app.post("/videos/{video_id}/reject", response_model=schemas.VideoResponse)
def reject_video(
    video_id: int,
    action_data: schemas.ApprovalAction,
    db: Session = Depends(database.get_db),
    authorized: bool = Depends(verify_admin_auth)
):
    """
    Admin REJECT action:
    - Stores optional rejection reason in DB.
    - Changes status to REJECTED.
    - Allows subsequent regeneration.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    reason = action_data.rejection_reason or action_data.comments or "Rejected during admin review."

    # Record rejection in approvals table
    approval = models.Approval(
        video_id=video.id,
        reviewer_id=1,
        action="REJECTED",
        is_approved=False,
        rejection_reason=reason,
        comments=action_data.comments,
        reviewed_at=datetime.utcnow()
    )
    db.add(approval)

    video.status = models.VideoStatus.REJECTED
    video.rejection_reason = reason
    video.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(video)

    return video


@app.post("/videos/{video_id}/regenerate")
def regenerate_video(
    video_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    authorized: bool = Depends(verify_admin_auth)
):
    """
    Admin/User REGENERATE action:
    - Resets status to GENERATING.
    - Restarts the generation pipeline.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video.status = models.VideoStatus.GENERATING
    video.error_message = None
    video.rejection_reason = None
    video.updated_at = datetime.utcnow()
    db.commit()

    background_tasks.add_task(run_video_pipeline, video_id)
    return {"status": "regenerating", "video_id": video_id}


@app.put("/videos/{video_id}/content", response_model=schemas.VideoResponse)
def update_video_content(
    video_id: int,
    update_data: schemas.VideoUpdate,
    db: Session = Depends(database.get_db),
    authorized: bool = Depends(verify_admin_auth)
):
    """
    Admin EDIT CONTENT action:
    - Saves edits to title, script, caption, hashtags, or scene breakdown.
    - Preserves original_plan without overwriting it.
    - Updates updated_at timestamp.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Preserve original plan if not yet preserved
    if not video.original_plan and video.plan:
        video.original_plan = dict(video.plan)

    plan = dict(video.plan or {})

    if update_data.title is not None:
        video.title = update_data.title
        plan["title"] = update_data.title

    if update_data.short_description is not None:
        plan["short_description"] = update_data.short_description

    if update_data.complete_narration is not None:
        video.script = update_data.complete_narration
        plan["complete_narration"] = update_data.complete_narration

    if update_data.caption is not None:
        video.caption = update_data.caption
        plan["caption"] = update_data.caption

    if update_data.hashtags is not None:
        video.hashtags = update_data.hashtags
        plan["hashtags"] = update_data.hashtags

    if update_data.scenes is not None:
        plan["scenes"] = [s.model_dump() for s in update_data.scenes]

    video.plan = plan
    video.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(video)

    return video


# ---------------------------------------------------------------------- #
# Listing & Detail Endpoints
# ---------------------------------------------------------------------- #
@app.get("/videos/", response_model=List[schemas.VideoResponse])
def get_videos(
    status: Optional[str] = Query(None, description="Filter by status (e.g. PENDING_APPROVAL)"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    query = db.query(models.Video)
    if status:
        # Match case-insensitively
        status_upper = status.upper()
        query = query.filter(models.Video.status == status_upper)

    videos = query.order_by(models.Video.id.desc()).offset(skip).limit(limit).all()
    return videos


@app.get("/videos/{video_id}", response_model=schemas.VideoResponse)
def get_video(video_id: int, db: Session = Depends(database.get_db)):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@app.get("/visual/provider-status", response_model=schemas.VisualProviderStatus)
def get_visual_provider_status():
    """Report which visual generation provider is active and hardware requirements."""
    import os
    provider_mode = os.getenv("VISUAL_PROVIDER", "auto")
    model_id = os.getenv("VISUAL_MODEL", "stabilityai/sd-turbo")
    replicate_model = os.getenv("REPLICATE_MODEL", "stability-ai/sdxl")

    try:
        active = get_visual_provider()
        active_name = active.name
        is_available = active.is_available
        message = active.availability_message()
    except Exception as exc:
        active_name = "unavailable"
        is_available = False
        message = str(exc)

    # Determine requirements based on provider
    requires_gpu = False
    recommended_vram_gb = 8
    recommended_ram_gb = 8
    
    if "replicate" in active_name.lower():
        requires_gpu = False  # Cloud-based
        recommended_vram_gb = 0
        recommended_ram_gb = 4
    elif "local" in active_name.lower():
        requires_gpu = True  # GPU recommended
        recommended_vram_gb = 4
        recommended_ram_gb = 8
    elif "mock" in active_name.lower():
        requires_gpu = False
        recommended_vram_gb = 0
        recommended_ram_gb = 2

    return schemas.VisualProviderStatus(
        provider=active_name,
        is_available=is_available,
        message=message,
        model=replicate_model if "replicate" in active_name.lower() else model_id,
        requires_gpu=requires_gpu,
        recommended_vram_gb=recommended_vram_gb,
        recommended_ram_gb=recommended_ram_gb,
    )


@app.get("/videos/{video_id}/scenes", response_model=List[schemas.SceneAssetResponse])
def get_video_scene_assets(video_id: int, db: Session = Depends(database.get_db)):
    """List all scene visual assets for a video."""
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    assets = (
        db.query(models.SceneAsset)
        .filter(models.SceneAsset.video_id == video_id)
        .order_by(models.SceneAsset.scene_number.asc())
        .all()
    )

    responses = []
    for asset in assets:
        data = schemas.SceneAssetResponse.model_validate(asset)
        if asset.image_path:
            data = data.model_copy(
                update={"image_url": f"/assets/video_{video_id}/scene_{asset.scene_number:03d}.png"}
            )
        responses.append(data)
    return responses


@app.post("/videos/{video_id}/scenes/{scene_number}/regenerate")
def regenerate_scene_visual(
    video_id: int,
    scene_number: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    authorized: bool = Depends(verify_admin_auth),
):
    """Regenerate visual for a single scene without re-running the entire pipeline."""
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    plan = dict(video.plan or {})
    scenes = plan.get("scenes", [])
    scene = next((s for s in scenes if s.get("scene_number") == scene_number), None)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene {scene_number} not found")

    base_dir = f"assets/video_{video_id}"
    width, height = _parse_resolution(video.resolution or "1080x1920")

    # Update status
    visual_status = dict(video.visual_generation_status or init_visual_status(scenes))
    update_scene_status(visual_status, scene_number, "generating")
    video.visual_generation_status = visual_status
    db.commit()

    def _regen_task():
        regen_db = database.SessionLocal()
        try:
            vid = regen_db.query(models.Video).filter(models.Video.id == video_id).first()
            if not vid:
                return
            current_plan = dict(vid.plan or {})
            current_scenes = current_plan.get("scenes", [])
            target = next((s for s in current_scenes if s.get("scene_number") == scene_number), None)
            if not target:
                return

            updated_scene = regenerate_single_scene(
                video_id=video_id,
                scene_number=scene_number,
                scene=target,
                all_scenes=current_scenes,
                base_dir=base_dir,
                visual_style=vid.visual_style or "realistic",
                db_session=regen_db,
                scene_asset_model=models.SceneAsset,
                width=width,
                height=height,
            )

            for i, s in enumerate(current_scenes):
                if s.get("scene_number") == scene_number:
                    current_scenes[i] = updated_scene
                    break
            current_plan["scenes"] = current_scenes
            vid.plan = current_plan

            vstatus = dict(vid.visual_generation_status or init_visual_status(current_scenes))
            update_scene_status(vstatus, scene_number, "completed")
            vid.visual_generation_status = vstatus
            vid.updated_at = datetime.utcnow()
            regen_db.commit()
        except Exception as exc:
            vid = regen_db.query(models.Video).filter(models.Video.id == video_id).first()
            if vid:
                vstatus = dict(vid.visual_generation_status or {})
                update_scene_status(vstatus, scene_number, "failed")
                vid.visual_generation_status = vstatus
                vid.error_message = f"Scene {scene_number} regeneration failed: {exc}"
                regen_db.commit()
        finally:
            regen_db.close()

    background_tasks.add_task(_regen_task)
    return {
        "status": "regenerating",
        "video_id": video_id,
        "scene_number": scene_number,
    }


@app.get("/videos/{video_id}/audit_log", response_model=schemas.AuditLogResponse)
def get_audit_log(video_id: int, db: Session = Depends(database.get_db)):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    approvals = db.query(models.Approval).filter(models.Approval.video_id == video_id).order_by(models.Approval.reviewed_at.desc()).all()
    attempts = db.query(models.GenerationAttempt).filter(models.GenerationAttempt.video_id == video_id).order_by(models.GenerationAttempt.attempt_number.asc()).all()
    
    return {
        "video_id": video_id,
        "approvals": approvals,
        "generation_attempts": attempts
    }


# ---------------------------------------------------------------------- #
# Phase 5: Social Media Account Connection & Platform Selection Endpoints
# ---------------------------------------------------------------------- #

@app.get("/social/platforms")
def get_supported_social_platforms():
    """
    Returns all supported platforms, capability specs, $0-cost status,
    developer registration requirements, and current configuration state.
    """
    return SocialProviderRegistry.list_all_platforms()


# In-memory temporary store for TikTok PKCE verifiers:
# {state: {"verifier": code_verifier, "created_at": timestamp}}
# One-time use: popped immediately upon retrieval.
_TIKTOK_PKCE_STORE: Dict[str, Dict[str, Any]] = {}


def _cleanup_expired_pkce_verifiers(ttl_seconds: int = 900) -> None:
    now = time.time()
    expired = [s for s, data in _TIKTOK_PKCE_STORE.items() if now - data.get("created_at", 0) > ttl_seconds]
    for s in expired:
        _TIKTOK_PKCE_STORE.pop(s, None)


@app.get("/social/oauth/authorize/{platform}")
@app.get("/social/oauth/{platform}/authorize")
@app.get("/social/oauth/login/{platform}")
@app.get("/social/oauth/{platform}/login")
def get_social_oauth_authorization_url(
    platform: str,
    request: Request,
    redirect_uri: Optional[str] = Query(None, description="Redirect URI for OAuth callback"),
    sandbox: bool = Query(False, description="Use sandbox mock provider instead of official API"),
    auto_redirect: Optional[bool] = Query(None, description="Redirect directly to provider auth URL")
):
    """
    Generates official OAuth consent URL (or sandbox redirect) for the platform.
    If called from a browser or /login endpoint, automatically redirects to the consent page.
    """
    try:
        if not redirect_uri:
            redirect_uri = f"http://localhost:8000/social/oauth/callback/{platform.lower().strip()}"

        provider = SocialProviderRegistry.get_provider(platform, use_sandbox=sandbox)
        csrf_state = secrets.token_urlsafe(16)

        if platform.lower() == "tiktok" and not sandbox:
            from social.tiktok import generate_pkce_verifier
            _cleanup_expired_pkce_verifiers()
            code_verifier = generate_pkce_verifier()
            _TIKTOK_PKCE_STORE[csrf_state] = {
                "verifier": code_verifier,
                "created_at": time.time()
            }
            auth_url = provider.get_authorization_url(state=csrf_state, redirect_uri=redirect_uri, code_verifier=code_verifier)
        else:
            auth_url = provider.get_authorization_url(state=csrf_state, redirect_uri=redirect_uri)

        is_browser = "text/html" in request.headers.get("accept", "")
        should_redirect = auto_redirect if auto_redirect is not None else (is_browser or "login" in request.url.path)
        if should_redirect:
            from starlette.responses import RedirectResponse
            return RedirectResponse(auth_url, status_code=307)

        return {"authorization_url": auth_url, "state": csrf_state, "platform": platform, "is_sandbox": sandbox}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/social/oauth/callback/{platform}")
@app.get("/social/oauth/{platform}/callback")
def handle_social_oauth_callback(
    request: Request,
    platform: str,
    code: Optional[str] = Query(None, description="Authorization code from OAuth provider"),
    error: Optional[str] = Query(None, description="Error code from OAuth provider"),
    error_description: Optional[str] = Query(None, description="Error description from OAuth provider"),
    redirect_uri: Optional[str] = Query(None, description="Redirect URI used in authorization (optional — derived from request URL if absent)"),
    state: Optional[str] = Query(None),
    sandbox: bool = Query(False),
    db: Session = Depends(database.get_db)
):
    """
    Exchanges OAuth code for access/refresh tokens, gets channel/profile info,
    encrypts credentials, and persists to social_accounts table.

    redirect_uri is optional: Google/Meta OAuth callback does NOT echo it back
    as a query parameter. When absent, it is derived from the request's own URL
    (scheme + host + path, without query string) — which is exactly the registered
    redirect URI that was used during the authorize step.
    """
    is_browser_request = "text/html" in request.headers.get("accept", "")

    # 1. Handle error response from OAuth provider
    if error:
        err_msg = f"OAuth provider error: {error}"
        if error_description:
            err_msg += f" - {error_description}"
        if is_browser_request:
            from starlette.responses import HTMLResponse
            return HTMLResponse(
                f"""<!DOCTYPE html><html><body style="background:#0F0F12;color:#F7F4F5;font-family:sans-serif;padding:40px;text-align:center;">
                <div style="max-width:500px;margin:auto;background:#15151B;padding:30px;border-radius:12px;border:1px solid #5B2129;">
                <h2 style="color:#E05260;">Connection Error</h2><p>{err_msg}</p>
                <a href="http://localhost:5173/?tab=social" style="color:#FFF;background:#C62845;padding:10px 20px;border-radius:8px;text-decoration:none;">Back to Studio</a>
                </div></body></html>""",
                status_code=400
            )
        raise HTTPException(status_code=400, detail=err_msg)

    if not code:
        err_msg = "Missing authorization code from OAuth provider."
        if is_browser_request:
            from starlette.responses import HTMLResponse
            return HTMLResponse(
                f"""<!DOCTYPE html><html><body style="background:#0F0F12;color:#F7F4F5;font-family:sans-serif;padding:40px;text-align:center;">
                <div style="max-width:500px;margin:auto;background:#15151B;padding:30px;border-radius:12px;border:1px solid #5B2129;">
                <h2 style="color:#E05260;">Connection Error</h2><p>{err_msg}</p>
                <a href="http://localhost:5173/?tab=social" style="color:#FFF;background:#C62845;padding:10px 20px;border-radius:8px;text-decoration:none;">Back to Studio</a>
                </div></body></html>""",
                status_code=400
            )
        raise HTTPException(status_code=400, detail=err_msg)

    # 2. Derive the redirect_uri from this request's own URL when not explicitly provided
    if not redirect_uri:
        redirect_uri = str(request.url).split("?")[0]

    # 3. Validate PKCE requirements for TikTok
    code_verifier = None
    if platform.lower() == "tiktok" and not sandbox:
        if not state:
            raise HTTPException(status_code=400, detail="Missing required OAuth state parameter for TikTok callback.")
        entry = _TIKTOK_PKCE_STORE.pop(state, None)
        if not entry or not entry.get("verifier"):
            raise HTTPException(status_code=400, detail="Missing or expired PKCE code_verifier for TikTok OAuth state.")
        code_verifier = entry["verifier"]

    try:
        provider = SocialProviderRegistry.get_provider(platform, use_sandbox=sandbox)
        if platform.lower() == "tiktok" and not sandbox:
            token_data = provider.exchange_code_for_tokens(
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier
            )
        else:
            token_data = provider.exchange_code_for_tokens(
                code=code,
                redirect_uri=redirect_uri
            )
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        
        info = provider.get_account_info(access_token)

        # Calculate expires_at if applicable
        token_expires_at = None
        if expires_in:
            from datetime import timedelta
            token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Check for existing account to update or create new
        account = db.query(models.SocialAccount).filter(
            models.SocialAccount.platform == platform.lower(),
            models.SocialAccount.account_id == info.get("account_id")
        ).first()

        if not account:
            account = models.SocialAccount(
                user_id=1,
                platform=platform.lower(),
                account_id=info.get("account_id"),
                is_mock=sandbox
            )
            db.add(account)

        account.account_name = info.get("account_name")
        account.account_handle = info.get("account_handle")
        # Store ONLY encrypted tokens! Never plain text
        account.encrypted_access_token = encrypt_token(access_token)
        account.encrypted_refresh_token = encrypt_token(refresh_token) if refresh_token else account.encrypted_refresh_token
        account.token_expires_at = token_expires_at
        account.status = "ACTIVE"
        account.metadata_json = {
            "avatar_url": info.get("avatar_url"),
            "profile_url": info.get("profile_url"),
            "page_name": info.get("page_name"),
            "page_id": info.get("page_id")
        }
        account.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(account)

        dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:8501")
        if is_browser_request:
            from starlette.responses import HTMLResponse
            return HTMLResponse(
                f"""<!DOCTYPE html><html>
                <head>
                    <meta http-equiv="refresh" content="2;url={dashboard_url}">
                    <title>{platform.title()} Connected</title>
                </head>
                <body style="background:#0F0F12;color:#F7F4F5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                    <div style="background:#15151B;border:1px solid #2B2B35;border-radius:16px;padding:36px;text-align:center;max-width:440px;box-shadow:0 10px 30px rgba(0,0,0,0.5);">
                        <div style="font-size:36px;margin-bottom:12px;">🎉</div>
                        <h2 style="font-size:20px;font-weight:700;margin:0 0 8px 0;color:#F7F4F5;">{platform.title()} Connected!</h2>
                        <p style="font-size:13px;color:#A9A4AA;margin:0 0 20px 0;">Account <strong>{account.account_handle or account.account_name}</strong> has been linked successfully.</p>
                        <a href="{dashboard_url}" style="display:inline-block;background:#C62845;color:#FFF;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;">Return to Studio Dashboard</a>
                    </div>
                </body></html>"""
            )

        return {
            "id": account.id,
            "platform": account.platform,
            "account_name": account.account_name,
            "account_handle": account.account_handle,
            "status": account.status,
            "is_mock": account.is_mock,
            "metadata_json": account.metadata_json,
            "created_at": account.created_at
        }
    except Exception as e:
        err_detail = f"OAuth connection failed: {str(e)}"
        dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:8501")
        if is_browser_request:
            from starlette.responses import HTMLResponse
            return HTMLResponse(
                f"""<!DOCTYPE html><html><body style="background:#0F0F12;color:#F7F4F5;font-family:sans-serif;padding:40px;text-align:center;">
                <div style="max-width:500px;margin:auto;background:#15151B;padding:30px;border-radius:12px;border:1px solid #5B2129;">
                <h2 style="color:#E05260;">Connection Error</h2><p style="font-size:13px;color:#F7F4F5;">{err_detail}</p>
                <a href="{dashboard_url}" style="color:#FFF;background:#C62845;padding:10px 20px;border-radius:8px;text-decoration:none;">Back to Studio Dashboard</a>
                </div></body></html>""",
                status_code=400
            )
        raise HTTPException(status_code=400, detail=err_detail)


@app.post("/social/accounts/sandbox", response_model=schemas.SocialAccountResponse)
def connect_sandbox_account(
    account_in: schemas.SocialAccountCreateSandbox,
    db: Session = Depends(database.get_db)
):
    """
    Connects an explicit Sandbox account without needing external developer credentials.
    Enforces the exact same validation constraints as the real provider.
    """
    platform = account_in.platform.lower().strip()
    if platform not in SocialProviderRegistry.SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

    mock_provider = SocialProviderRegistry.get_provider(platform, use_sandbox=True)
    tokens = mock_provider.exchange_code_for_tokens("sandbox_code", "http://localhost")
    info = mock_provider.get_account_info(tokens["access_token"])

    acc_name = account_in.account_name or info.get("account_name")
    acc_handle = account_in.account_handle or info.get("account_handle")

    # Check if a sandbox account for this platform already exists
    account = db.query(models.SocialAccount).filter(
        models.SocialAccount.platform == platform,
        models.SocialAccount.is_mock == True
    ).first()

    if not account:
        account = models.SocialAccount(
            user_id=1,
            platform=platform,
            account_id=info.get("account_id"),
            is_mock=True
        )
        db.add(account)

    account.account_name = acc_name
    account.account_handle = acc_handle
    account.encrypted_access_token = encrypt_token(tokens["access_token"])
    account.encrypted_refresh_token = encrypt_token(tokens.get("refresh_token"))
    account.status = "ACTIVE"
    account.metadata_json = {
        "avatar_url": info.get("avatar_url"),
        "profile_url": info.get("profile_url")
    }
    account.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(account)

    return account


@app.post("/social/accounts/manual-token", response_model=schemas.SocialAccountResponse)
def connect_manual_token_account(
    payload: schemas.SocialAccountManualToken,
    db: Session = Depends(database.get_db)
):
    """
    Connects an account directly via pre-generated access token / page token.
    Useful for Meta Graph API explorer tokens, long-lived tokens, or YouTube developer tokens.
    """
    platform = payload.platform.lower().strip()
    if platform not in SocialProviderRegistry.SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

    acc_name = payload.account_name or f"{platform.capitalize()} Creator Account"
    acc_handle = payload.account_handle or f"@{platform}_creator"
    account_id = f"manual_{platform}_{int(time.time())}"

    account = db.query(models.SocialAccount).filter(
        models.SocialAccount.platform == platform,
        models.SocialAccount.is_mock == False
    ).first()

    if not account:
        account = models.SocialAccount(
            user_id=1,
            platform=platform,
            account_id=account_id,
            is_mock=False
        )
        db.add(account)

    account.account_name = acc_name
    account.account_handle = acc_handle
    account.encrypted_access_token = encrypt_token(payload.access_token)
    if payload.refresh_token:
        account.encrypted_refresh_token = encrypt_token(payload.refresh_token)
    if payload.expires_in:
        account.token_expires_at = datetime.utcnow() + timedelta(seconds=payload.expires_in)
    account.status = "ACTIVE"
    account.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(account)

    return account


@app.get("/social/accounts", response_model=List[schemas.SocialAccountResponse])
def get_connected_accounts(
    platform: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    """
    Lists all connected social accounts for the user.
    Tokens are NEVER returned in this response.
    """
    query = db.query(models.SocialAccount)
    if platform:
        query = query.filter(models.SocialAccount.platform == platform.lower().strip())
    accounts = query.order_by(models.SocialAccount.id.asc()).all()
    return accounts


@app.delete("/social/accounts/{account_id}")
def disconnect_social_account(
    account_id: int,
    db: Session = Depends(database.get_db)
):
    """
    Disconnects/removes a connected social account.
    """
    account = db.query(models.SocialAccount).filter(models.SocialAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Social account not found")

    db.delete(account)
    db.commit()
    return {"status": "disconnected", "account_id": account_id}


# ---------------------------------------------------------------------- #
# Publishing Configuration & Validation Endpoints
# ---------------------------------------------------------------------- #

@app.get("/videos/{video_id}/publishing-config", response_model=Optional[schemas.PublishingConfigResponse])
def get_video_publishing_config(
    video_id: int,
    db: Session = Depends(database.get_db)
):
    """
    Retrieves the current publishing configuration for an approved video.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    config = db.query(models.PublishingConfiguration).filter(
        models.PublishingConfiguration.video_id == video_id
    ).order_by(models.PublishingConfiguration.id.desc()).first()

    return config


@app.post("/videos/{video_id}/publishing-config", response_model=schemas.PublishingConfigResponse)
def save_video_publishing_config(
    video_id: int,
    payload: schemas.PublishingConfigCreate,
    validate: bool = Query(False, description="Run validation immediately after saving"),
    db: Session = Depends(database.get_db)
):
    """
    Saves or updates the publishing configuration and platform settings for a video.
    Tracks: Video -> PublishingConfiguration -> Platform -> ConnectedAccount -> PlatformMetadata -> Status.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Video must be approved before saving publishing config
    if video.status not in [models.VideoStatus.APPROVED, models.VideoStatus.READY_TO_SCHEDULE]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot configure publishing for video in '{video.status}' status. Video must be APPROVED first."
        )

    # Find or create PublishingConfiguration
    config = db.query(models.PublishingConfiguration).filter(
        models.PublishingConfiguration.video_id == video_id
    ).first()

    if not config:
        config = models.PublishingConfiguration(
            video_id=video_id,
            status="DRAFT"
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    # Clear old settings and re-create from payload
    db.query(models.PlatformPublishingSetting).filter(
        models.PlatformPublishingSetting.configuration_id == config.id
    ).delete()

    for s_in in payload.settings:
        setting = models.PlatformPublishingSetting(
            configuration_id=config.id,
            platform=s_in.platform.lower().strip(),
            account_id=s_in.account_id,
            platform_metadata=s_in.platform_metadata,
            status="CONFIGURED",
            is_validated=False
        )
        db.add(setting)

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    if validate:
        # Run validation logic immediately
        validate_video_publishing_config(video_id=video_id, db=db)
        db.refresh(config)

    return config


@app.post("/videos/{video_id}/publishing-config/validate", response_model=schemas.PublishingValidationResult)
def validate_video_publishing_config(
    video_id: int,
    db: Session = Depends(database.get_db)
):
    """
    Validates publishing configuration before a video can proceed:
    1. Video exists
    2. Video is approved (status APPROVED or READY_TO_SCHEDULE)
    3. Video file exists on disk
    4. Connected social account exists and is ACTIVE for each selected platform
    5. Required platform metadata exists and adheres to platform constraints
    6. If all pass -> marks config as READY_TO_SCHEDULE and video as READY_TO_SCHEDULE!
    7. If any fail -> returns structured platform-specific errors.
    """
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 1 & 2. Video is approved
    if video.status not in [models.VideoStatus.APPROVED, models.VideoStatus.READY_TO_SCHEDULE]:
        return schemas.PublishingValidationResult(
            is_valid=False,
            status="FAILED",
            video_id=video_id,
            errors={"video": [f"Video is not approved (current status: {video.status}). Only APPROVED videos can be scheduled."]},
            message="Video must be approved before configuring publishing."
        )

    # 3. Video file exists on disk
    if not video.video_path or not os.path.exists(video.video_path):
        return schemas.PublishingValidationResult(
            is_valid=False,
            status="FAILED",
            video_id=video_id,
            errors={"video": ["Video file does not exist on disk or has not been generated."]},
            message="Video file is missing."
        )

    config = db.query(models.PublishingConfiguration).filter(
        models.PublishingConfiguration.video_id == video_id
    ).first()

    if not config or not config.settings:
        return schemas.PublishingValidationResult(
            is_valid=False,
            status="FAILED",
            video_id=video_id,
            errors={"platforms": ["No social media platforms have been selected or configured."]},
            message="Please select at least one social media platform."
        )

    all_errors: Dict[str, List[str]] = {}
    total_settings = len(config.settings)
    validated_count = 0

    for setting in config.settings:
        plat = setting.platform.lower().strip()
        p_errors: List[str] = []

        # 4. Connected account exists and is active
        account = db.query(models.SocialAccount).filter(
            models.SocialAccount.id == setting.account_id
        ).first()

        if not account:
            p_errors.append(f"No connected account linked for {plat.capitalize()}. Please connect an account first.")
        elif account.status != "ACTIVE":
            p_errors.append(f"Connected account '{account.account_name}' ({plat.capitalize()}) is {account.status}. Please reconnect.")

        # 5. Metadata validation against official platform provider rules
        meta = setting.platform_metadata or {}
        is_val, val_errs = SocialProviderRegistry.validate_metadata(
            platform=plat,
            metadata=meta,
            video_path=video.video_path
        )
        p_errors.extend(val_errs)

        # Update setting state
        setting.validation_errors = p_errors
        setting.is_validated = (len(p_errors) == 0)
        setting.status = "VALIDATED" if setting.is_validated else "ERROR"
        setting.updated_at = datetime.utcnow()

        if p_errors:
            all_errors[plat] = p_errors
        else:
            validated_count += 1

    if all_errors:
        config.status = "FAILED"
        db.commit()
        return schemas.PublishingValidationResult(
            is_valid=False,
            status="FAILED",
            video_id=video_id,
            configuration_id=config.id,
            errors=all_errors,
            message="Validation failed for one or more platforms. Please correct the errors."
        )

    # All platforms passed validation!
    # Transition milestone: READY_TO_SCHEDULE
    config.status = "READY_TO_SCHEDULE"
    video.status = models.VideoStatus.READY_TO_SCHEDULE
    video.updated_at = datetime.utcnow()
    db.commit()

    return schemas.PublishingValidationResult(
        is_valid=True,
        status="READY_TO_SCHEDULE",
        video_id=video_id,
        configuration_id=config.id,
        errors={},
        message=f"Success! All {validated_count} platform configuration(s) are validated. Video is Ready to Schedule!"
    )

