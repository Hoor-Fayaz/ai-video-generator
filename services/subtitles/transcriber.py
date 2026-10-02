import os
import shutil
import textwrap
import re
from typing import List, Dict, Any, Optional
import whisper
from whisper.utils import get_writer
import imageio_ffmpeg


def _ensure_ffmpeg_in_path():
    """Ensure ffmpeg executable from imageio_ffmpeg is in PATH for whisper."""
    try:
        exe_path = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(exe_path)
        target = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        if not os.path.exists(target):
            shutil.copyfile(exe_path, target)
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception as e:
        print(f"[FFmpeg PATH Warning]: {e}")


def _format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp H:MM:SS.cc"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cc = int(round((seconds - int(seconds)) * 100))
    if cc >= 100:
        cc = 99
    return f"{h}:{m:02d}:{s:02d}.{cc:02d}"


def _format_srt_time(seconds: float) -> str:
    """Format seconds into SRT timestamp HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_ass_script(
    words_data: List[Dict[str, Any]],
    output_ass_path: str,
    width: int = 1080,
    height: int = 1920,
    chunk_size: int = 3,
):
    """
    Builds an Advanced SubStation Alpha (.ass) subtitle script with
    Alex Hormozi / MrBeast viral karaoke highlight effect:
    - 2-4 words per line chunk in bold uppercase
    - Active word illuminated in bright vibrant gold/yellow (&H0000E6FF&)
    - Surrounding words in clean bright white (&H00FFFFFF&)
    - Crisp heavy drop shadow and black outline for 100% legibility
    """
    font_size = max(24, round(height * 0.036))  # ~70px on 1080x1920
    margin_v = max(50, round(height * 0.20))    # ~384px above bottom

    header = f"""[Script Info]
Title: Dynamic Viral Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralActive,Arial,{font_size},&H00FFFFFF,&H0000E6FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,5,3,2,50,50,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines = []

    # Clean and filter word items
    clean_words = []
    for w in words_data:
        text = str(w.get("word", "")).strip().upper()
        # Strip extraneous punctuation for display
        text_clean = re.sub(r"[^\w\s\$\%\'\-]", "", text)
        if text_clean:
            clean_words.append({
                "word": text_clean,
                "start": max(0.0, float(w.get("start", 0.0))),
                "end": max(0.05, float(w.get("end", 0.05))),
            })

    if not clean_words:
        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(header)
        return

    # Chunk words into batches of 2-3 words (or max ~24 chars)
    chunks = []
    current_chunk = []
    current_len = 0

    for w in clean_words:
        w_len = len(w["word"])
        if len(current_chunk) >= chunk_size or (current_len + w_len > 22 and len(current_chunk) >= 2):
            chunks.append(current_chunk)
            current_chunk = [w]
            current_len = w_len
        else:
            current_chunk.append(w)
            current_len += w_len + 1

    if current_chunk:
        chunks.append(current_chunk)

    # Build dialogue lines for each word step within chunk
    for chunk in chunks:
        chunk_words = [c["word"] for c in chunk]
        for idx, active_word in enumerate(chunk):
            w_start = active_word["start"]
            # Word duration extends to next word start or end
            if idx + 1 < len(chunk):
                w_end = max(w_start + 0.1, chunk[idx + 1]["start"])
            else:
                w_end = max(w_start + 0.2, active_word["end"])

            start_str = _format_ass_time(w_start)
            end_str = _format_ass_time(w_end)

            # Build line text: active word has highlight tag, others have white tag
            line_parts = []
            for j, w_text in enumerate(chunk_words):
                if j == idx:
                    # Vibrant Gold/Yellow highlight
                    line_parts.append(f"{{\\c&H0000E6FF&}}{w_text}{{\\c&H00FFFFFF&}}")
                else:
                    line_parts.append(w_text)

            styled_text = " ".join(line_parts)
            dialogue_lines.append(
                f"Dialogue: 0,{start_str},{end_str},ViralActive,,0,0,0,,{styled_text}"
            )

    full_ass = header + "\n".join(dialogue_lines) + "\n"
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass)


def _create_fallback_subtitles(
    audio_path: str,
    base_dir: str,
    filename_no_ext: str,
    fallback_text: str = "Video Narration",
) -> tuple[str, str]:
    """Creates matched .srt and .ass fallback files using proportional timing."""
    try:
        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip
        audio = AudioFileClip(audio_path)
        duration = float(audio.duration)
        audio.close()
    except Exception:
        duration = 10.0

    words = fallback_text.split() if fallback_text else ["Video", "Narration"]
    word_count = max(len(words), 1)
    per_word_sec = duration / word_count

    simulated_words = []
    for i, w in enumerate(words):
        w_start = i * per_word_sec
        w_end = (i + 1) * per_word_sec
        simulated_words.append({"word": w, "start": w_start, "end": w_end})

    srt_path = os.path.join(base_dir, f"{filename_no_ext}.srt")
    ass_path = os.path.join(base_dir, f"{filename_no_ext}.ass")

    # Generate ASS
    _build_ass_script(simulated_words, ass_path)

    # Generate SRT
    srt_lines = []
    chunk_size = 4
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        st = i * per_word_sec
        et = min(duration, (i + len(chunk)) * per_word_sec)
        idx = (i // chunk_size) + 1
        srt_lines.append(f"{idx}\n{_format_srt_time(st)} --> {_format_srt_time(et)}\n{' '.join(chunk)}\n")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    return srt_path, ass_path


def generate_subtitles(
    audio_path: str,
    output_dir: str,
    filename_no_ext: str,
    fallback_text: str = "",
    width: int = 1080,
    height: int = 1920,
) -> str:
    """
    Transcribes audio using OpenAI Whisper with word timestamps and generates
    both viral-styled .ass captions and compliant .srt subtitles.
    Returns path to the primary subtitles file (.ass preferred).
    """
    os.makedirs(output_dir, exist_ok=True)
    final_srt_path = os.path.join(output_dir, f"{filename_no_ext}.srt")
    final_ass_path = os.path.join(output_dir, f"{filename_no_ext}.ass")

    _ensure_ffmpeg_in_path()

    try:
        print("[Subtitles] Loading Whisper model for precise word timestamps...")
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, word_timestamps=True)

        # 1. Extract all word level timestamps across segments
        extracted_words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                extracted_words.append(w)

        if extracted_words:
            print(f"[Subtitles] Extracted {len(extracted_words)} timed words. Generating dynamic viral .ass captions...")
            _build_ass_script(extracted_words, final_ass_path, width=width, height=height)

        # 2. Write standard SRT format as companion
        srt_writer = get_writer("srt", output_dir)
        srt_writer(result, audio_path, {"max_line_width": 28, "max_line_count": 2, "highlight_words": False})

        audio_basename = os.path.basename(audio_path)
        expected_srt_path = os.path.join(output_dir, audio_basename + ".srt")
        if os.path.exists(expected_srt_path) and expected_srt_path != final_srt_path:
            if os.path.exists(final_srt_path):
                os.remove(final_srt_path)
            os.rename(expected_srt_path, final_srt_path)

        if os.path.exists(final_ass_path):
            return final_ass_path
        if os.path.exists(final_srt_path):
            return final_srt_path

    except Exception as e:
        print(f"[Whisper Warning] Word-level transcription failed ({e}), using animated timing fallback...")
        srt_p, ass_p = _create_fallback_subtitles(audio_path, output_dir, filename_no_ext, fallback_text)
        return ass_p if os.path.exists(ass_p) else srt_p

    if os.path.exists(final_ass_path):
        return final_ass_path
    if os.path.exists(final_srt_path):
        return final_srt_path

    srt_p, ass_p = _create_fallback_subtitles(audio_path, output_dir, filename_no_ext, fallback_text)
    return ass_p if os.path.exists(ass_p) else srt_p
