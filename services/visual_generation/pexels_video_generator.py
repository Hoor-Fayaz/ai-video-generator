"""Pexels and Pixabay HD Stock Video Provider for high-end video clip generation."""

import os
import re
import requests
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from .base import (
    VisualGenerationProvider,
    VisualGenerationRequest,
    VisualGenerationResult,
    validate_generated_video,
)

load_dotenv()


def _clean_query(text: str) -> str:
    """Extract pristine search keywords for stock video retrieval."""
    if not text:
        return ""
    # Remove punctuation and generic words
    words = re.sub(r"[^\w\s]", " ", text).split()
    banned = {
        "photorealistic", "documentary", "cinematic", "vertical", "composition",
        "framing", "shot", "showing", "scene", "view", "realistic", "4k", "8k",
        "hyperrealistic", "unreal", "render", "depth", "field", "lens", "close",
        "wide", "angle", "high", "low", "lighting", "detailed", "macro",
        "the", "a", "an", "and", "or", "in", "on", "at", "of", "with", "by", "for",
        "fact", "facts", "top", "instantly", "reduce", "reduces", "benefit", "benefits",
        "reason", "reasons", "way", "ways", "explaining", "explained", "origin", "origins",
        "discovery", "principle", "principles", "underlying", "mechanism", "mechanisms",
        "structural", "diversity", "environmental", "interaction", "interactions",
        "modern", "understanding", "global", "significance", "empirically", "governed"
    }
    filtered = [w for w in words if len(w) > 2 and w.lower() not in banned]
    return " ".join(filtered[:3])


class PexelsVideoGenerator(VisualGenerationProvider):
    """
    Fetches real high-definition, cinematic stock video clips via Pexels Video API
    and Pixabay Video API with guaranteed cross-scene visual diversity.
    """

    # Tracks used video URLs per output directory to ensure no two scenes share the same clip
    _used_urls_by_dir: Dict[str, set] = {}

    @property
    def name(self) -> str:
        return "pexels:video-hd"

    @property
    def is_available(self) -> bool:
        return bool(os.getenv("PEXELS_API_KEY") or os.getenv("PIXABAY_API_KEY"))

    def availability_message(self) -> str:
        if os.getenv("PEXELS_API_KEY"):
            return "Pexels HD Video Provider ready."
        if os.getenv("PIXABAY_API_KEY"):
            return "Pixabay HD Video Provider ready."
        return "Pexels API key not set. Set PEXELS_API_KEY in .env to enable direct 1080p/4K stock video clip downloads."

    def _search_pexels(
        self,
        query: str,
        orientation: str = "portrait",
        scene_number: int = 1,
        exclude_urls: Optional[set] = None
    ) -> Optional[str]:
        api_key = os.getenv("PEXELS_API_KEY")
        if not api_key:
            return None

        headers = {"Authorization": api_key.strip()}
        url = "https://api.pexels.com/videos/search"
        params = {
            "query": query,
            "orientation": orientation,
            "per_page": 20,
            "size": "medium",
        }

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                videos = data.get("videos", [])
                candidates = []
                for vid in videos:
                    files = vid.get("video_files", [])
                    hd_files = [
                        f for f in files
                        if f.get("file_type") == "video/mp4" and (f.get("width") or 0) >= 720
                    ]
                    if hd_files:
                        hd_files.sort(key=lambda x: abs((x.get("width") or 0) - 1080))
                        link = hd_files[0].get("link")
                        if link and (exclude_urls is None or link not in exclude_urls):
                            candidates.append(link)
                    elif files:
                        mp4_files = [f for f in files if f.get("file_type") == "video/mp4"]
                        if mp4_files:
                            link = mp4_files[0].get("link")
                            if link and (exclude_urls is None or link not in exclude_urls):
                                candidates.append(link)

                if candidates:
                    idx = (scene_number - 1) % len(candidates)
                    return candidates[idx]
        except Exception as e:
            print(f"[Pexels Video Warning]: {e}")
        return None

    def _search_pixabay(
        self,
        query: str,
        scene_number: int = 1,
        exclude_urls: Optional[set] = None
    ) -> Optional[str]:
        api_key = os.getenv("PIXABAY_API_KEY")
        if not api_key:
            return None

        url = "https://pixabay.com/api/videos/"
        params = {
            "key": api_key.strip(),
            "q": query,
            "per_page": 20,
        }

        try:
            resp = requests.get(url, params=params, timeout=12)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                candidates = []
                for hit in hits:
                    v_hit = hit.get("videos", {})
                    # Try large, then medium, then small
                    for size in ["large", "medium", "small"]:
                        if size in v_hit and v_hit[size].get("url"):
                            v_url = v_hit[size]["url"]
                            if exclude_urls is None or v_url not in exclude_urls:
                                candidates.append(v_url)
                                break

                if candidates:
                    idx = (scene_number - 1) % len(candidates)
                    return candidates[idx]
        except Exception as e:
            print(f"[Pixabay Video Warning]: {e}")
        return None

    def generate(self, request: VisualGenerationRequest) -> VisualGenerationResult:
        # Determine target output path (ensure .mp4 extension for video)
        base_out = os.path.splitext(request.output_path)[0]
        video_out = base_out + ".mp4"
        out_dir = os.path.dirname(os.path.abspath(video_out)) or "."
        os.makedirs(out_dir, exist_ok=True)

        # Track used URLs for this specific video directory so scenes never repeat
        used_urls = self._used_urls_by_dir.setdefault(out_dir, set())

        orientation = "portrait" if request.height >= request.width else "landscape"
        scene_num = request.scene_number or 1

        # Candidate queries prioritized by scene-specific focus
        queries = []
        if request.stock_query:
            clean_sq = _clean_query(request.stock_query)
            if clean_sq:
                queries.append(clean_sq)
        if request.visual_prompt:
            clean_vp = _clean_query(request.visual_prompt)
            if clean_vp and clean_vp not in queries:
                queries.append(clean_vp)
        if request.claim:
            clean_c = _clean_query(request.claim)
            if clean_c and clean_c not in queries:
                queries.append(clean_c)
        if request.topic:
            clean_t = _clean_query(request.topic)
            if clean_t and clean_t not in queries:
                queries.append(clean_t)

        video_url = None
        used_query = ""

        # Try with strict exclusion to prevent repeat clips
        for q in queries:
            if not q:
                continue
            video_url = self._search_pexels(q, orientation, scene_number=scene_num, exclude_urls=used_urls)
            if not video_url:
                video_url = self._search_pixabay(q, scene_number=scene_num, exclude_urls=used_urls)
            if video_url:
                used_query = q
                break

        # Fallback queries if no clip found yet
        if not video_url:
            fallbacks = ["nature", "landscape", "calm", "relaxing", "trees"]
            fallback_q = fallbacks[(scene_num - 1) % len(fallbacks)]
            video_url = self._search_pexels(fallback_q, orientation, scene_number=scene_num, exclude_urls=used_urls)
            if not video_url:
                video_url = self._search_pixabay(fallback_q, scene_number=scene_num, exclude_urls=used_urls)
            if video_url:
                used_query = fallback_q

        # If still nothing, relax exclusion
        if not video_url and queries:
            first_q = queries[0]
            video_url = self._search_pexels(first_q, orientation, scene_number=scene_num) or self._search_pixabay(first_q, scene_number=scene_num)
            used_query = first_q

        if video_url:
            used_urls.add(video_url)

        if not video_url:
            return VisualGenerationResult(
                success=False,
                output_path=request.output_path,
                provider_name=self.name,
                is_mock=False,
                error_message=f"No matching HD stock video found for queries: {queries[:3]}"
            )

        # Download the video clip
        try:
            print(f"[Pexels Video] Downloading HD clip for query '{used_query}'...")
            with requests.get(video_url, stream=True, timeout=40) as r:
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
                metadata={"download_url": video_url, "search_query": used_query}
            )

        except Exception as e:
            return VisualGenerationResult(
                success=False,
                output_path=video_out,
                provider_name=self.name,
                is_mock=False,
                error_message=f"Download failed: {str(e)}"
            )
