import os
import shutil
import subprocess
import tempfile
from typing import List, Optional


def _get_ffmpeg_bin() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def parse_duration(dur_str) -> float:
    try:
        import re
        if isinstance(dur_str, (int, float)):
            return float(dur_str)
        match = re.search(r"\d+\.?\d*", str(dur_str))
        return float(match.group()) if match else 5.0
    except Exception:
        return 5.0


def _is_video_file(file_path: str) -> bool:
    """Check if file is a video format."""
    if not file_path:
        return False
    ext = os.path.splitext(file_path)[1].lower()
    return ext in [".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"]


def _get_video_duration(ffmpeg_bin: str, file_path: str) -> float:
    """Extract duration of a media file via ffmpeg."""
    try:
        import re
        cmd = [ffmpeg_bin, "-i", file_path]
        res = subprocess.run(cmd, capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
        if m:
            h, m_, s = m.groups()
            return int(h) * 3600 + int(m_) * 60 + float(s)
    except Exception:
        pass
    return 5.0


def _prepare_scene_video(
    ffmpeg_bin: str,
    video_path: str,
    duration: float,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> bool:
    """
    Normalizes a video clip for scene composition:
    - Automatically loops if clip is shorter than scene duration, or trims if longer
    - Scales and center-crops to target dimensions without distortion
    - Enhances contrast & saturation for a cinematic documentary look
    - Applies smooth fade in/out transitions
    - Strips clip audio so voiceover audio is crystal clear
    """
    clip_dur = _get_video_duration(ffmpeg_bin, video_path)
    fade_dur = min(0.35, duration * 0.08)

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"eq=contrast=1.05:saturation=1.08:brightness=0.01,"
        f"fade=t=in:st=0:d={fade_dur},"
        f"fade=t=out:st={max(duration - fade_dur, 0):.3f}:d={fade_dur}"
    )

    cmd = [ffmpeg_bin, "-y"]
    if clip_dur < duration - 0.1:
        # Loop video to cover full duration
        cmd.extend(["-stream_loop", "-1", "-i", video_path, "-t", str(duration)])
    else:
        cmd.extend(["-i", video_path, "-t", str(duration)])

    cmd.extend([
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-an",
        output_path,
    ])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000


def _animate_scene_image(
    ffmpeg_bin: str,
    image_path: str,
    duration: float,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    animation_style: str = "cinematic",
) -> bool:
    """
    Apply Ken Burns 2.0 animation with smooth sinusoidal easing and filmic grading.
    """
    total_frames = max(int(duration * fps), 1)
    fade_dur = min(0.35, duration * 0.08)

    scene_idx = 0
    try:
        import re
        m = re.search(r"scene_(\d+)", os.path.basename(image_path))
        if m:
            scene_idx = int(m.group(1))
    except Exception:
        pass

    mode = scene_idx % 4
    if mode == 0:
        # Smooth push-in
        zoom_expr = f"'1.0+0.14*sin(on/{total_frames}*1.57)'"
        x_expr = f"'(iw-iw/zoom)/2'"
        y_expr = f"'(ih-ih/zoom)*0.35'"
    elif mode == 1:
        # Smooth horizontal drift
        zoom_expr = f"'1.08+0.06*sin(on/{total_frames}*3.14)'"
        x_expr = f"'(iw-iw/zoom)*(0.2+0.6*on/{total_frames})'"
        y_expr = f"'(ih-ih/zoom)/2'"
    elif mode == 2:
        # Pull-out reveal
        zoom_expr = f"'1.16-0.12*sin(on/{total_frames}*1.57)'"
        x_expr = f"'(iw-iw/zoom)*0.5'"
        y_expr = f"'(ih-ih/zoom)*0.45'"
    else:
        # Diagonal tilt
        zoom_expr = f"'1.04+0.10*on/{total_frames}'"
        x_expr = f"'(iw-iw/zoom)*(0.7-0.4*on/{total_frames})'"
        y_expr = f"'(ih-ih/zoom)*(0.3+0.4*on/{total_frames})'"

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z={zoom_expr}:x={x_expr}:y={y_expr}:"
        f"d={total_frames}:s={width}x{height}:fps={fps},"
        f"eq=contrast=1.05:saturation=1.08:brightness=0.01,"
        f"fade=t=in:st=0:d={fade_dur},"
        f"fade=t=out:st={max(duration - fade_dur, 0):.3f}:d={fade_dur}"
    )

    cmd = [
        ffmpeg_bin, "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-an",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000


def _concat_videos(ffmpeg_bin: str, clip_paths: list, output_path: str) -> bool:
    """Concatenate prepared scene clips into a unified video stream."""
    if not clip_paths:
        return False
    if len(clip_paths) == 1:
        shutil.copyfile(clip_paths[0], output_path)
        return True

    list_file = output_path + ".concat.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            safe = p.replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        os.remove(list_file)
    except Exception:
        pass
    return result.returncode == 0 and os.path.exists(output_path)


def _add_audio(ffmpeg_bin: str, video_path: str, audio_path: str, output_path: str) -> bool:
    """Add voiceover audio track to master video."""
    cmd = [
        ffmpeg_bin, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path)


def _burn_subtitles(
    ffmpeg_bin: str,
    video_path: str,
    sub_path: str,
    output_path: str,
    work_dir: str,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """
    Burn subtitles with viral aesthetics:
    - Prefers .ass files with word-by-word karaoke highlight styling
    - Falls back to .srt with bold high-contrast viral typography
    - Positioned ~20% above bottom edge (safe from mobile UI overlay)
    """
    # Check if an .ass companion file exists in the directory
    ass_companion = os.path.splitext(sub_path)[0] + ".ass"
    if os.path.exists(ass_companion):
        sub_path = ass_companion

    ext = os.path.splitext(sub_path)[1].lower()
    local_sub_name = "subtitles" + ext
    local_sub_path = os.path.join(work_dir, local_sub_name)

    try:
        if os.path.abspath(sub_path) != os.path.abspath(local_sub_path):
            shutil.copyfile(sub_path, local_sub_path)
    except Exception as e:
        print(f"[Subtitle Copy Warning]: {e}")

    if ext == ".ass":
        subtitle_filter = f"ass={local_sub_name}"
    else:
        # High-impact viral SRT styling
        font_size = max(24, round(height * 0.038))  # ~72px for 1920h
        margin_v = max(60, round(height * 0.20))    # ~384px above bottom edge
        margin_h = max(30, round(width * 0.08))     # ~86px left/right margins

        subtitle_style = (
            f"PlayResX={width},"
            f"PlayResY={height},"
            "FontName=Arial,"
            f"FontSize={font_size},"
            "PrimaryColour=&H00FFFFFF,"   # Clean bright white
            "OutlineColour=&H00000000,"   # Bold black stroke
            "BackColour=&H80000000,"      # Drop shadow
            "BorderStyle=1,"              # Outline + shadow
            "Outline=4.5,"                # Thick 4.5px crisp stroke
            "Shadow=2.5,"                 # Punchy drop shadow
            f"MarginV={margin_v},"
            f"MarginL={margin_h},"
            f"MarginR={margin_h},"
            "Alignment=2,"                # Centered horizontally
            "Bold=1"                      # Heavy bold weight
        )
        subtitle_filter = f"subtitles={local_sub_name}:force_style='{subtitle_style}'"

    video_name = os.path.basename(video_path)
    output_name = os.path.basename(output_path)

    cmd = [
        ffmpeg_bin, "-y",
        "-i", video_name,
        "-vf", subtitle_filter,
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "19",
        "-movflags", "+faststart",
        output_name,
    ]

    result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path)


def compose_video(
    image_paths: list = None,
    durations: list = None,
    audio_path: str = "",
    srt_path: str = "",
    output_path: str = "",
    width: int = 1080,
    height: int = 1920,
    media_paths: list = None,
) -> str:
    """
    Full composition pipeline supporting both high-end video clips and animated images:
    1. Prepares each scene:
       - Video clips (.mp4) -> trimmed/looped, scaled/cropped, color-enhanced, faded
       - Image clips (.png) -> animated with Ken Burns 2.0 smooth camera movements
    2. Concatenates all scene clips
    3. Adds high-fidelity voiceover audio
    4. Burns styled captions (word-highlighted .ass or viral-styled .srt)
    """
    input_paths = media_paths or image_paths or []
    if not input_paths:
        raise ValueError("No media paths provided for video composition")

    abs_output = os.path.abspath(output_path)
    work_dir = os.path.dirname(abs_output)
    os.makedirs(work_dir, exist_ok=True)

    ffmpeg_bin = _get_ffmpeg_bin()
    temp_clips = []
    temp_with_audio = os.path.join(work_dir, "temp_with_audio.mp4")
    temp_concat = os.path.join(work_dir, "temp_concat.mp4")

    try:
        # Step 1: Prepare each scene clip
        for i, media_file in enumerate(input_paths):
            dur = parse_duration(durations[i]) if (durations and i < len(durations)) else 5.0
            clip_path = os.path.join(work_dir, f"prep_scene_{i:03d}.mp4")

            if _is_video_file(media_file):
                print(f"[Composer] Scene {i+1}: Processing high-end video clip ({media_file})...")
                success = _prepare_scene_video(
                    ffmpeg_bin, media_file, dur, clip_path, width, height, fps=30
                )
            else:
                print(f"[Composer] Scene {i+1}: Applying Ken Burns 2.0 motion to visual ({media_file})...")
                success = _animate_scene_image(
                    ffmpeg_bin, media_file, dur, clip_path, width, height, fps=30
                )

            if not success:
                raise RuntimeError(f"Failed to prepare scene {i + 1} from media: {media_file}")
            temp_clips.append(clip_path)

        # Step 2: Concatenate scene clips
        print("[Composer] Concatenating scene clips...")
        if not _concat_videos(ffmpeg_bin, temp_clips, temp_concat):
            raise RuntimeError("Failed to concatenate scene clips")

        # Step 3: Add voiceover audio
        if audio_path and os.path.exists(audio_path):
            print("[Composer] Merging voiceover audio...")
            if not _add_audio(ffmpeg_bin, temp_concat, audio_path, temp_with_audio):
                shutil.copyfile(temp_concat, temp_with_audio)
        else:
            shutil.copyfile(temp_concat, temp_with_audio)

        # Step 4: Burn subtitles
        sub_candidate = srt_path
        if not sub_candidate or not os.path.exists(sub_candidate):
            # Check for voiceover.ass or voiceover.srt in audio directory
            if audio_path:
                audio_dir = os.path.dirname(audio_path)
                for cand in ["voiceover.ass", "voiceover.srt", "subtitles.ass", "subtitles.srt"]:
                    p = os.path.join(audio_dir, cand)
                    if os.path.exists(p):
                        sub_candidate = p
                        break

        if sub_candidate and os.path.exists(sub_candidate):
            print(f"[Composer] Burning styled captions from {sub_candidate}...")
            if not _burn_subtitles(ffmpeg_bin, temp_with_audio, sub_candidate, abs_output, work_dir, width, height):
                print("[Composer Warning] Subtitle burning failed, falling back to clean video")
                shutil.copyfile(temp_with_audio, abs_output)
        else:
            shutil.copyfile(temp_with_audio, abs_output)

    finally:
        for p in temp_clips + [temp_concat, temp_with_audio]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    return abs_output
