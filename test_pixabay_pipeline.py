"""
Test full end-to-end video generation pipeline with Pixabay HD stock clips.
"""

import os
import sys
import time
import requests

API_BASE = "http://127.0.0.1:8000"

def run_test():
    print("=" * 60)
    print("TESTING FULL PIPELINE WITH PIXABAY HD VIDEO CLIPS")
    print("=" * 60)

    # 1. Health check
    try:
        r = requests.get(f"{API_BASE}/docs", timeout=5)
        print(f"[1/6] API is reachable (HTTP {r.status_code})")
    except Exception as e:
        print(f"Error connecting to {API_BASE}: {e}")
        return False

    # 2. Submit prompt for video creation
    prompt_payload = {
        "prompt": "Top 3 relaxing nature facts that instantly reduce stress.",
        "duration": "15-30 seconds",
        "language": "English",
        "style": "Cinematic Nature",
        "target_platform": "TikTok",
        "visual_style": "realistic",
        "visual_provider": "auto"
    }

    print("\n[2/6] Submitting video creation request...")
    r = requests.post(f"{API_BASE}/videos/", json=prompt_payload, timeout=30)
    if r.status_code != 200:
        print(f"Failed to create video: {r.status_code} - {r.text}")
        return False

    video_data = r.json()
    video_id = video_data["id"]
    print(f"-> Video created! ID: {video_id}")
    print(f"-> Title: {video_data.get('title')}")
    plan = video_data.get("plan") or {}
    scenes = plan.get("scenes", [])
    print(f"-> Planned scenes: {len(scenes)}")
    for i, sc in enumerate(scenes):
        print(f"   Scene {i+1}: {sc.get('topic', '')} | query: {sc.get('stock_query', sc.get('visual_prompt', ''))[:40]}")

    # 3. Trigger video generation
    print(f"\n[3/6] Starting generation pipeline for Video {video_id}...")
    gen_opts = {
        "visual_style": "realistic",
        "visual_provider": "auto"
    }
    r = requests.post(f"{API_BASE}/videos/{video_id}/generate", json=gen_opts, timeout=30)
    if r.status_code != 200:
        print(f"Failed to trigger generation: {r.status_code} - {r.text}")
        return False
    print("-> Generation initiated in background.")

    # 4. Monitor progress until completion or error
    print("\n[4/6] Polling generation status...")
    max_wait = 600  # 10 minutes max for HD downloads + composition
    start_time = time.time()
    last_stage = None

    while time.time() - start_time < max_wait:
        time.sleep(4)
        try:
            r = requests.get(f"{API_BASE}/videos/{video_id}", timeout=10)
            if r.status_code != 200:
                print(f"Error fetching status: {r.status_code}")
                continue
            cur = r.json()
            status = cur.get("status")
            stage = cur.get("generation_stage")

            if stage != last_stage:
                print(f"   [{int(time.time() - start_time)}s] Stage: {stage} | Status: {status}")
                last_stage = stage

            if status in ["PENDING_APPROVAL", "GENERATED", "APPROVED", "QA_PENDING"]:
                print(f"\n-> Generation finished successfully! Status: {status}")
                break
            elif status == "FAILED":
                print(f"\n-> Generation failed: {cur.get('error_message')}")
                return False
        except Exception as e:
            print(f"Polling warning: {e}")

    elapsed = round(time.time() - start_time, 1)

    # 5. Verify assets on disk
    print(f"\n[5/6] Verifying generated assets (took {elapsed}s)...")
    r = requests.get(f"{API_BASE}/videos/{video_id}", timeout=10)
    cur = r.json()
    video_path = cur.get("video_path")
    audio_path = cur.get("audio_path")
    subtitles_path = cur.get("subtitles_path")

    print(f"-> Final video path: {video_path}")
    print(f"-> Audio path: {audio_path}")
    print(f"-> Subtitles path: {subtitles_path}")

    if not video_path or not os.path.exists(video_path):
        print(f"ERROR: Final video file does not exist at {video_path}")
        return False

    size_bytes = os.path.getsize(video_path)
    size_mb = round(size_bytes / (1024 * 1024), 2)
    print(f"-> Video size: {size_mb} MB ({size_bytes} bytes)")

    # Check scene media files
    asset_dir = os.path.dirname(video_path)
    print(f"\n[6/6] Inspecting scene files in {asset_dir}...")
    scene_files = [f for f in os.listdir(asset_dir) if f.startswith("scene_")]
    for sf in sorted(scene_files):
        sfp = os.path.join(asset_dir, sf)
        sz = round(os.path.getsize(sfp) / 1024, 1)
        ext = os.path.splitext(sf)[1]
        print(f"   - {sf} ({ext}, {sz} KB)")

    print("\n" + "=" * 60)
    print("PIPELINE TEST PASSED! Video generated successfully with Pixabay clips.")
    print(f"Playable at: {video_path}")
    print(f"View in Dashboard: http://127.0.0.1:8501")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
