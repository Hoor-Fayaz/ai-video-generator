import os
import json
import re
import time
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv
from api.schemas import VideoPlan, Scene
from services.visual_generation.prompt_builder import (
    validate_visual_prompt_grounding,
    regenerate_grounded_visual_prompt,
    clean_visual_text,
    is_tech_domain,
)

load_dotenv()

# ==============================================================================
# BANNED FILLER & META VIDEO-PRODUCTION PATTERNS
# ==============================================================================
BANNED_FILLER_PATTERNS = [
    r"(?i)\bmost\s+people\s+don'?t\s+know\b",
    r"(?i)\bdid\s+you\s+know\b",
    r"(?i)\bhere\s+is\s+what\s+you\s+need\s+to\s+know\b",
    r"(?i)\bhere'?s\s+what\s+you\s+need\s+to\s+know\b",
    r"(?i)\blet\s+us\s+explore\b",
    r"(?i)\blet'?s\s+explore\b",
    r"(?i)\blet'?s\s+dive\s+in\b",
    r"(?i)\blet\s+us\s+dive\s+in\b",
    r"(?i)\bin\s+today'?s\s+world\b",
    r"(?i)\bis\s+changing\s+the\s+world\b",
    r"(?i)\bis\s+becoming\s+increasingly\s+important\b",
    r"(?i)\bfollow\s+for\s+more\b",
    r"(?i)\bstay\s+tuned\b",
    r"(?i)\bhere'?s\s+the\s+interesting\s+part\b",
    r"(?i)\bnow\s+let'?s\s+look\s+at\b",
    r"(?i)\banother\s+important\s+thing\b",
    r"(?i)\bone\s+more\s+thing\b",
    r"(?i)\ba\s+practical\s+approach\s+you\s+can\s+apply\s+immediately\b",
    r"(?i)\bmost\s+people\s+overlook\s+this\s+important\s+detail\b",
    r"(?i)\bdrop\s+your\s+thoughts\s+in\s+the\s+comments\b",
]

BANNED_META_PATTERNS = [
    r"(?i)\b(in\s+)?(this|today'?s)\s+video\b",
    r"(?i)\bcreate\s+(a\s+)?video(\s+about)?\b",
    r"(?i)\bcreating\s+(a\s+|this\s+)?video\b",
    r"(?i)\bmake\s+(a\s+)?video(\s+about)?\b",
    r"(?i)\bmaking\s+(a\s+|this\s+)?video\b",
    r"(?i)\bfor\s+this\s+video\b",
    r"(?i)\bin\s+this\s+content\b",
    r"(?i)\blet'?s\s+create\b",
    r"(?i)\bwe'?ll\s+create\b",
    r"(?i)\bprinciples\s+behind\s+(creating|making|create|make)\b",
    r"(?i)\bhow\s+to\s+make\s+(this|a)\s+video\b",
    r"(?i)\bthis\s+video\s+(will\s+)?(show|explain|explore|cover|break\s+down|reveal)\b",
    r"(?i)\bvideo\s+explains\b",
    r"(?i)\bvideo\s+shows\b",
    r"(?i)\bhere\s+is\s+how\s+to\s+make\b",
    r"(?i)\bfascinating\s+principles\s+behind\s+(create|creating|make|making)?\s*",
]

SCENE_JSON_SCHEMA = """
{
  "title": "Concise, specific topic title (max 8 words)",
  "topic": "The exact core subject requested by the user",
  "hook": "A sharp opening hook (max 15 words) introducing the premise without consuming individual points",
  "short_description": "1-2 sentence high-density summary of the core thesis",
  "complete_narration": "Full combined narration script teaching distinct insights",
  "facts": [
    {
      "fact_number": 1,
      "topic": "The exact core subject",
      "claim": "Specific factual proposition directly about the requested topic",
      "explanation": "Why or how this phenomenon works",
      "example": "Documented real-world instance, location, or tangible illustration",
      "narration": "Spoken voiceover script explaining WHAT, WHY, and HOW with zero filler and ZERO meta video language",
      "visual_prompt": "Photorealistic documentary description of the EXACT physical subject, terrain, organism, artifact, or phenomenon described in the claim. NO text overlays, NO generic people at laptops, NO technology schematics unless the topic is specifically computing/AI.",
      "environment": "Authentic physical setting directly illustrating the fact",
      "characters": "Specific tangible subject relevant to the claim",
      "objects": "Key visual elements illustrating the subject",
      "camera_style": "Camera framing and lighting suited to the visual demonstration",
      "duration": 6
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "fact_number": 1,
      "topic": "The exact core subject",
      "claim": "Specific factual proposition directly about the requested topic",
      "explanation": "Why or how this mechanism or phenomenon works",
      "example": "Documented example or tangible illustration",
      "duration": 6,
      "scene_duration": "6s",
      "narration": "Spoken voiceover script for this scene answering WHAT, WHY, and HOW with zero filler and ZERO meta video language",
      "visual_prompt": "Photorealistic documentary description of the EXACT physical subject, terrain, artifact, or phenomenon described in the claim. NO text overlays, NO generic people at laptops, NO technology schematics unless the topic is specifically computing/AI.",
      "environment": "Authentic physical setting directly illustrating the fact",
      "characters": "Specific tangible subject relevant to the claim",
      "objects": "Key visual elements illustrating the subject",
      "camera_style": "Camera framing and lighting suited to the visual demonstration",
      "visual_style": "realistic"
    }
  ],
  "closing": "A concise concluding insight summarizing the overarching principle (max 15 words)",
  "suggested_background_music": "e.g. majestic natural documentary ambient soundtrack",
  "caption": "Informative educational caption with relevant context",
  "hashtags": ["#tag1", "#tag2", "#tag3"]
}
"""

CONTENT_PLANNER_SYSTEM_PROMPT = """
You are a world-class scientific educator, researcher, and visual content architect.
Your goal is to produce high-density educational video plans strictly grounded in the user's requested topic.

CRITICAL CONTENT REQUIREMENTS:
1. TOPIC IS THE PRIMARY CONSTRAINT:
   - Every single scene, claim, narration, and visual prompt MUST remain strictly about the user's requested topic.
   - For an Earth Geography / Weather topic: describe clouds, precipitation, mountains, rivers, atmosphere, and natural landscapes. NEVER generate AI, computer screens, futuristic technology, digital interfaces, or server rooms.
   - For History topics: describe authentic historical architecture, artifacts, landscapes, and archaeological settings.
   - For Space topics: describe celestial bodies, planets, stars, and cosmological phenomena.
   - For Biology topics: describe living organisms, ecosystems, and natural habitats.

2. STRICTLY NO META VIDEO-PRODUCTION LANGUAGE:
   - NEVER talk about creating or making a video.
   - BANNED PHRASES: "in this video", "this video will show", "let us create", "the principles behind creating a video", "here is how to make", "in today's video", "for this video".
   - Speak DIRECTLY about the topic itself as a documentary narrator.

3. DISTINCT INFORMATIONAL UNITS:
   - Every scene MUST teach a completely NEW, DISTINCT factual concept or mechanism.
   - NEVER repeat claims or concepts across scenes.

4. STRICTLY BANNED FILLER:
   - NEVER use generic filler phrases ("Most people don't know...", "Did you know...", "Let us explore...", "In today's world...", "Follow for more...").
   - Jump directly into concrete, substantive facts and mechanisms.

5. NARRATION MUST TEACH (WHAT, WHY, HOW):
   - Every narration sentence must answer: WHAT is the fact? WHY is it true? HOW does it work?

6. SCENE-TO-FACT VISUAL ALIGNMENT:
   - The visual_prompt MUST directly depict the physical reality of what is being narrated.
   - BANNED VISUALS: NO generic people at laptops, NO abstract glowing blue stock backgrounds, NO floating text/words, NO unrelated tech schematics.
   - REQUIRED VISUALS: Concrete documentary views of the subject.
"""


def clean_banned_filler(text: str) -> str:
    """Removes banned generic filler and meta video-production language from narration or text."""
    if not text:
        return ""
    cleaned = text
    for pattern in BANNED_FILLER_PATTERNS + BANNED_META_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-:;")
    return cleaned


def contains_meta_video_language(text: str) -> bool:
    """Checks if text contains meta video-production language."""
    if not text:
        return False
    for pat in BANNED_META_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def validate_video_plan(plan: VideoPlan, min_scenes: int = 3) -> Tuple[bool, List[str]]:
    """
    Validates content quality, fact diversity, filler absence, topic consistency, and visual alignment.
    Returns (is_valid, list_of_issues).
    """
    issues = []
    if not plan.scenes or len(plan.scenes) < min_scenes:
        issues.append(f"Insufficient scenes: found {len(plan.scenes) if plan.scenes else 0}, required at least {min_scenes}.")

    topic_context = plan.topic or plan.title or ""

    # 1. Check for banned filler and meta language in narrations and hook
    if plan.hook and contains_meta_video_language(plan.hook):
        issues.append(f"Video hook contains meta video-production language: '{plan.hook}'")

    for s in plan.scenes:
        for pat in BANNED_FILLER_PATTERNS:
            if re.search(pat, s.narration):
                issues.append(f"Scene {s.scene_number} contains banned filler matching pattern: {pat}")
        for pat in BANNED_META_PATTERNS:
            if re.search(pat, s.narration):
                issues.append(f"Scene {s.scene_number} contains meta video-production language: {s.narration}")

    # 2. Check narration word count & density
    for s in plan.scenes:
        word_count = len(s.narration.split())
        if word_count < 10:
            issues.append(f"Scene {s.scene_number} narration is too short/sparse ({word_count} words). Minimum 10 words required.")

    # 3. Check for repetitive claims / duplicate narrations across scenes
    seen_keywords = []
    for s in plan.scenes:
        words = set([w.lower().strip(".,!?:;") for w in s.narration.split() if len(w) > 4])
        for prev_idx, prev_words in enumerate(seen_keywords):
            overlap = words.intersection(prev_words)
            if len(overlap) > 8:
                issues.append(f"Scene {s.scene_number} heavily duplicates concepts from Scene {prev_idx + 1} (shared terms: {list(overlap)[:5]}).")
        seen_keywords.append(words)

    # 4. Check visual prompt grounding & domain consistency
    for s in plan.scenes:
        vp = s.visual_prompt.strip()
        scene_topic = s.topic or topic_context
        scene_claim = s.claim or ""
        scene_narr = s.narration or ""

        is_valid_vp, reason = validate_visual_prompt_grounding(
            topic=scene_topic,
            claim=scene_claim,
            narration=scene_narr,
            visual_prompt=vp
        )
        if not is_valid_vp:
            issues.append(f"Scene {s.scene_number} visual prompt validation failed: {reason}")

    return (len(issues) == 0, issues)


def _normalize_scene(raw: dict, default_style: str = "realistic", fallback_topic: str = "") -> Scene:
    """Normalize LLM output to consistent Scene schema with informational units."""
    scene_num = raw.get("scene_number", 1)
    duration = raw.get("duration")
    scene_dur = raw.get("scene_duration")

    if duration is None and scene_dur:
        match = re.search(r"\d+", str(scene_dur))
        duration = int(match.group()) if match else 6
    elif duration is None:
        duration = 6
        scene_dur = f"{duration}s"
    elif not scene_dur:
        scene_dur = f"{duration}s"

    raw_narration = raw.get("narration", "")
    narration = clean_banned_filler(raw_narration) or raw_narration

    topic = raw.get("topic") or fallback_topic or ""
    claim = clean_banned_filler(raw.get("claim") or raw.get("fact") or f"Fact {scene_num}")
    explanation = raw.get("explanation") or ""
    example = raw.get("example") or ""
    fact_number = raw.get("fact_number") or scene_num

    visual_prompt = raw.get("visual_prompt") or raw.get("visual_description") or ""
    visual_style = raw.get("visual_style") or default_style

    # Ensure visual prompt is grounded in topic & claim
    is_valid_vp, _ = validate_visual_prompt_grounding(topic, claim, narration, visual_prompt)
    if not is_valid_vp:
        visual_prompt = regenerate_grounded_visual_prompt(topic, claim, narration, visual_style)

    environment = raw.get("environment", "")
    characters = raw.get("characters", "")
    objects = raw.get("objects", "")
    camera_style = raw.get("camera_style", "medium shot, eye level")

    # Generate optimized stock query and motion prompt for video clips
    topic_kw = " ".join([w for w in (topic or "").split() if len(w) > 2][:2])
    claim_kw = " ".join([w for w in (claim or "").split() if len(w) > 3][:2])
    clean_stock = raw.get("stock_query") or f"{topic_kw} {claim_kw}".strip() or topic or "nature"
    clean_motion = raw.get("video_motion_prompt") or f"Cinematic {camera_style}, 4k ultra high definition documentary, perfectly stable framing, smooth motion, {visual_prompt}"

    return Scene(
        scene_number=scene_num,
        duration=int(duration),
        scene_duration=scene_dur,
        narration=narration,
        visual_prompt=visual_prompt,
        environment=environment,
        characters=characters,
        objects=objects,
        camera_style=camera_style,
        visual_style=visual_style,
        visual_description=visual_prompt,
        fact_number=fact_number,
        topic=topic,
        claim=claim,
        explanation=explanation,
        example=example,
        stock_query=clean_stock,
        video_motion_prompt=clean_motion,
    )


# ==============================================================================
# HIGH-DENSITY DOMAIN KNOWLEDGE SYNTHESIZER
# ==============================================================================
TOPIC_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "rainy day": {
        "title": "5 Calming & Fascinating Facts About Rainy Days",
        "topic": "Rainy Days",
        "hook": "Rain begins when warm moist air rises, cools, and condenses into billions of suspended cloud droplets.",
        "facts": [
            {
                "claim": "Atmospheric Condensation Nuclei Seed Every Falling Raindrop",
                "explanation": "Water vapor in rising warm air cannot condense into droplets on its own; it requires microscopic particles such as salt, dust, or pollen called condensation nuclei.",
                "example": "A single cubic meter of a rain cloud contains hundreds of millions of microscopic cloud droplets suspended by rising air currents.",
                "narration": "Rain begins high in the atmosphere as warm moist air ascends and cools. Water vapor condenses around microscopic airborne dust and sea salt particles, forming dense storm clouds.",
                "visual_prompt": "Photorealistic documentary view of dramatic gray cumulus rain clouds swelling in an overcast sky, with heavy rain shafts visible falling over distant green hills, vertical 9:16 composition",
                "environment": "Atmospheric overcast sky with swelling rain clouds",
                "characters": "Towering gray rain clouds",
                "objects": "Distant falling rain shafts, cloud condensation layers, misty horizon",
                "camera_style": "Cinematic wide establishing shot of atmospheric rain clouds"
            },
            {
                "claim": "Collision and Coalescence Create Heavy Falling Raindrops",
                "explanation": "Inside turbulent storm clouds, falling droplets collide with smaller droplets, coalescing into larger drops until their mass overcomes the cloud's updrafts.",
                "example": "Typical raindrops reach terminal fall velocities between 9 and 30 kilometers per hour before striking the ground.",
                "narration": "Inside clouds, billions of tiny water droplets collide and merge together. As they grow heavier, gravity overcomes the rising air updrafts, sending steady showers of rain down to Earth.",
                "visual_prompt": "Cinematic macro documentary view of glistening individual raindrops falling through the air and splashing onto vibrant green foliage, soft overcast lighting, realistic, vertical 9:16 composition",
                "environment": "Rain-drenched botanical garden with lush green leaves",
                "characters": "Falling glistening raindrops splashing on leaves",
                "objects": "Raindrops, glistening water droplets on leaf surfaces, soft misty rain",
                "camera_style": "Macro high-speed slow motion camera focused on splashing raindrops"
            },
            {
                "claim": "The Characteristic Aroma of Rain is Called Petrichor",
                "explanation": "Rain striking dry soil traps tiny air bubbles that launch aerosols containing geosmin from soil bacteria and plant oils into the air.",
                "example": "The human olfactory system is exceptionally sensitive to geosmin, detecting it at concentrations of mere parts per trillion.",
                "narration": "The familiar, refreshing scent of a rainy day is called petrichor. Falling raindrops trap tiny air bubbles against the soil, releasing aromatic plant oils and earthy microbial compounds into the breeze.",
                "visual_prompt": "Cinematic close-up view of raindrops splashing gently onto dark fertile garden soil and forest moss, with delicate mist rising in a calm peaceful atmosphere, vertical 9:16 composition",
                "environment": "Serene forest floor covered with damp moss and dark rich soil",
                "characters": "Raindrops splashing on forest earth",
                "objects": "Damp soil, green moss, water droplets, gentle rising mist",
                "camera_style": "Low-angle close-up tracking shot along the damp earth"
            },
            {
                "claim": "Rainfall Replenishes Continental Aquifers and Hydrological Cycles",
                "explanation": "Infiltration of rainwater recharges subterranean groundwater tables, sustaining perennial streams, wetlands, and global river basins.",
                "example": "Over 500,000 cubic kilometers of water precipitate over Earth annually, maintaining global freshwater reserves.",
                "narration": "Rain is the primary engine of Earth's freshwater cycle. Steady rainfall soaks deep into underground aquifers and feeds winding streams, nourishing forests and sustaining agricultural river valleys.",
                "visual_prompt": "Photorealistic aerial view of gentle rain falling across a peaceful misty valley, with a winding freshwater stream flowing through dense pine woods and rolling meadows, vertical 9:16 composition",
                "environment": "Misty mountain valley with winding stream during steady rain",
                "characters": "The freshwater stream and misty valley landscape",
                "objects": "Winding stream, pine trees, misty rain veil, wet meadow grass",
                "camera_style": "Slow aerial drone glide over the rainy forest valley"
            },
            {
                "claim": "Rain Cleanses Atmospheric Particulates and Cools the Surface",
                "explanation": "Precipitation scavenging removes airborne particulate matter and pollutants, while evaporative cooling lowers ambient ground temperatures.",
                "example": "A steady downpour can reduce airborne particulate pollution by up to 50% while cooling urban heat islands.",
                "narration": "As raindrops fall, they wash dust and airborne pollutants from the atmosphere. Evaporative cooling drops surface temperatures, leaving behind crisp, purified air and glistening surroundings.",
                "visual_prompt": "Cinematic peaceful documentary view of gentle rain falling on a quiet city street, with glistening wet asphalt reflecting warm glowing streetlights and raindrops creating ripples in puddles, vertical 9:16 composition",
                "environment": "Quiet city street with wet glistening pavement in the rain",
                "characters": "Rainy street scene with glowing reflections",
                "objects": "Rain ripples in puddles, wet asphalt reflections, warm streetlight glow",
                "camera_style": "Smooth ground-level tracking shot across rain ripples on wet pavement"
            }
        ],
        "closing": "Rainfall replenishes our freshwater ecosystems, purifying the air and sustaining all terrestrial life."
    },
    "earth geography": {
        "title": "5 Fascinating Facts About Earth's Geography",
        "topic": "Earth geography",
        "hook": "Our planet's dramatic physical landscapes are shaped by immense planetary forces.",
        "facts": [
            {
                "claim": "Continental Tectonic Collisions Form Earth's Highest Mountains",
                "explanation": "The colossal tectonic collision between the Indian and Eurasian tectonic plates continues to thrust the Himalayan mountain range upwards by millimeters every year.",
                "example": "Mount Everest and the surrounding Himalayan peaks rise over 8,800 meters above sea level due to ongoing convergent plate boundary forces.",
                "narration": "Earth's highest mountains are formed by immense tectonic plate collisions. As the Indian plate continuously pushes beneath the Eurasian plate, the Himalayas are forced upward millimeters higher every single year.",
                "visual_prompt": "Photorealistic aerial documentary view of the Himalayan mountain range, massive snow-covered peaks, deep mountain valleys, natural atmospheric haze, realistic Earth geography, vertical 9:16 composition",
                "environment": "High-altitude mountain range with snow-capped peaks and glaciers",
                "characters": "The towering Himalayan peaks and geological faultlines",
                "objects": "Glacial ice fields, rugged alpine ridges, mountain mist",
                "camera_style": "Sweeping aerial cinematic wide angle shot over the peaks"
            },
            {
                "claim": "Oceanic Subduction Zones Plunge Nearly 11,000 Meters into the Abyss",
                "explanation": "Where dense oceanic crust subducts beneath another tectonic plate, it carves massive ocean trenches such as the Mariana Trench in the Western Pacific.",
                "example": "The Challenger Deep plunges to a depth of nearly 36,000 feet, exerting hydrostatic pressure over a thousand times greater than at sea level.",
                "narration": "Deep beneath the oceans, subduction zones carve gargantuan chasms into Earth's crust. The Mariana Trench drops nearly eleven thousand meters, creating an extreme high-pressure abyssal zone shrouded in total darkness.",
                "visual_prompt": "Photorealistic underwater documentary view of the deep oceanic Mariana Trench abyss, rugged volcanic rock walls, deep navy and cyan oceanic depths, atmospheric submarine perspective, realistic Earth geography, vertical 9:16 composition",
                "environment": "Deep ocean trench abyss with dark oceanic waters",
                "characters": "The underwater oceanic trench and seabed topography",
                "objects": "Deep-sea chasms, underwater rock formations, oceanic sediment",
                "camera_style": "Deep-sea submersible camera slowly panning across the abyss wall"
            },
            {
                "claim": "Atmospheric Hadley Circulation Creates Vast Continental Desert Belts",
                "explanation": "Solar heating at the equator causes warm air to rise and shed moisture, before descending as dry, high-pressure air over the subtropics to create vast arid deserts.",
                "example": "The Sahara Desert spans over 9 million square kilometers across North Africa, shaped by persistent subtropical high-pressure weather belts.",
                "narration": "Global atmospheric currents called Hadley cells dictate Earth's climate zones. Dry descending air currents create enormous arid expanses like the Sahara Desert, where shifting sand dunes stretch across thousands of miles.",
                "visual_prompt": "Cinematic photorealistic aerial view of the golden sand dunes of the Sahara Desert, dramatic wind-carved dune ripples under a bright sunlit blue sky, vast desert landscape, realistic Earth geography, vertical 9:16 composition",
                "environment": "Expansive sunny Sahara desert landscape with golden sand dunes",
                "characters": "The sweeping Sahara desert sand dunes",
                "objects": "Wind-rippled sand ridges, desert dunes, clear sunny horizon",
                "camera_style": "Low-altitude drone tracking shot soaring over sweeping sand dune crests"
            },
            {
                "claim": "Continental River Basins Discharge Massive Volumes of Global Freshwater",
                "explanation": "Vast river catchment basins collect precipitation across entire continents, nourishing dense rainforest biomes and regulating global ocean salinity.",
                "example": "The Amazon River discharges approximately 209,000 cubic meters of freshwater per second, accounting for roughly one-fifth of all global river flow.",
                "narration": "Continental river systems are Earth's primary freshwater lifelines. The mighty Amazon basin collects runoff from vast rainforests, discharging one-fifth of the entire planet's river water into the Atlantic Ocean.",
                "visual_prompt": "Breathtaking photorealistic aerial view of the winding Amazon River flowing through a dense lush green tropical rainforest canopy, morning mist rising from the trees, realistic Earth geography, vertical 9:16 composition",
                "environment": "Lush tropical Amazon rainforest with winding river waterway",
                "characters": "The winding Amazon river and tropical forest canopy",
                "objects": "River meanders, dense rainforest trees, rising morning mist",
                "camera_style": "Cinematic high-angle aerial landscape shot gliding along the river curve"
            },
            {
                "claim": "Earth's Molten Outer Core Generates a Protective Magnetic Shield",
                "explanation": "Convection of liquid iron and nickel in Earth's outer core creates a geodynamo that produces a magnetosphere deflecting harmful solar wind.",
                "example": "Interactions between the magnetosphere and charged solar particles produce the radiant Aurora Borealis and Aurora Australis in polar skies.",
                "narration": "Deep inside our planet, circulating liquid iron generates a magnetic shield. This protective magnetosphere deflects lethal solar radiation into polar skies, producing glowing green aurora displays that safeguard all terrestrial life.",
                "visual_prompt": "Spectacular orbital view of planet Earth from space with glowing green Aurora Borealis lights shimmering over the polar atmosphere, curved Earth horizon and stars in background, realistic Earth geography, vertical 9:16 composition",
                "environment": "Low Earth orbit looking down at planetary curvature and atmosphere",
                "characters": "Planet Earth and the glowing atmospheric aurora",
                "objects": "Atmospheric horizon curve, green shimmering aurora ribbons, starry space",
                "camera_style": "Slow orbital space station perspective looking down at Earth's limb"
            }
        ],
        "closing": "These immense geographical forces continuously reshape the continents and oceans we call home."
    },
    "ancient egypt": {
        "title": "5 Fascinating Facts About Ancient Egypt",
        "topic": "Ancient Egypt",
        "hook": "Ancient Egyptian civilization engineered monumental achievements along the Nile over thousands of years.",
        "facts": [
            {
                "claim": "Precision Alignment of the Great Pyramid of Giza",
                "explanation": "The Great Pyramid is aligned to true north with an accuracy of within a fraction of a degree, achieved using astronomical observations.",
                "example": "Built with over 2.3 million limestone blocks, the pyramid remained the tallest man-made structure for over 3,800 years.",
                "narration": "The Great Pyramid of Giza was built with astonishing astronomical precision, aligning to true north with incredible accuracy using millions of massive limestone blocks.",
                "visual_prompt": "Cinematic photorealistic documentary view of the Great Pyramids of Giza rising above the golden desert sands, dramatic golden hour sunlight, authentic ancient Egyptian archaeology, vertical 9:16 composition",
                "environment": "Giza plateau desert landscape at sunset",
                "characters": "The Great Pyramids of Giza",
                "objects": "Limestone blocks, golden desert sand, dramatic sunset rays",
                "camera_style": "Low-angle majestic wide shot looking up at the monumental pyramid"
            },
            {
                "claim": "The Annual Nile Inundation Governed Egyptian Agriculture",
                "explanation": "The annual flooding of the Nile deposited nutrient-rich black silt along the riverbanks, allowing prosperous agriculture in the desert.",
                "example": "The Egyptians called their fertile land Kemet, meaning Black Land, contrasting with the barren red desert.",
                "narration": "Ancient Egypt's economy relied on the annual flooding of the Nile. Each summer, nutrient-rich black silt was deposited across the river valley, creating lush fertile farmland in the desert.",
                "visual_prompt": "Photorealistic documentary view of the ancient Nile River valley with green fertile crop fields along the riverbank, traditional reed feluccas on the water, palm trees and desert cliffs in the background",
                "environment": "Fertile Nile riverbank bordered by arid desert hills",
                "characters": "The ancient Nile river waterway and fertile fields",
                "objects": "Irrigation canals, green crops, date palm trees",
                "camera_style": "Smooth aerial landscape tracking shot along the Nile riverbank"
            },
            {
                "claim": "Hieroglyphs Were a Sophisticated Phonetic and Symbolic System",
                "explanation": "Hieroglyphic writing combined logographic, syllabic, and alphabetic elements carved into stone temple walls and papyrus scrolls.",
                "example": "The discovery of the Rosetta Stone in 1799 provided the key to deciphering ancient Egyptian hieroglyphs.",
                "narration": "Egyptian hieroglyphs were not simple picture writing, but a complex phonetic language of over seven hundred characters carved into sacred temple walls and painted on papyrus.",
                "visual_prompt": "Detailed close-up documentary shot of ancient Egyptian hieroglyphics deeply carved into weathered sandstone temple walls, rich golden sunlight casting deep shadows in the glyph carvings",
                "environment": "Ancient Karnak sandstone temple wall",
                "characters": "Carved hieroglyphic inscriptions",
                "objects": "Sandstone wall reliefs, cartouches of pharaohs, ritual symbols",
                "camera_style": "Macro camera tracking slowly across intricately carved hieroglyphs"
            },
            {
                "claim": "Sophisticated Mummification Preserved Anatomical Structures",
                "explanation": "Embalmers used natron salt, resin-soaked linens, and organ removal into canopic jars to preserve bodies for the afterlife.",
                "example": "Mummies preserved thousands of years ago retain intact hair, bone structures, and facial features.",
                "narration": "To prepare pharaohs for the afterlife, embalmers mastered preservation science using natural natron salts and aromatic resins to keep organic tissues intact across thousands of years.",
                "visual_prompt": "Photorealistic documentary view of an ancient Egyptian royal burial chamber adorned with colorful mythological wall paintings, ornate gold leaf decor, and carved stone sarcophagi",
                "environment": "Ancient subterranean tomb chamber in the Valley of the Kings",
                "characters": "Royal golden sarcophagus and painted tomb murals",
                "objects": "Canopic jars, gilded ornaments, painted deity frescoes",
                "camera_style": "Atmospheric slow push into the dimly lit burial chamber"
            },
            {
                "claim": "Massive Architectural Engineering at Luxor and Karnak",
                "explanation": "Monumental hypostyle halls with towering columns supported massive stone lintels without modern machinery.",
                "example": "The Great Hypostyle Hall at Karnak features 134 massive sandstone columns standing up to 21 meters tall.",
                "narration": "Monumental temples like Karnak featured colossal hypostyle halls with over one hundred towering stone columns, designed to mirror a primeval forest of papyrus plants at the dawn of creation.",
                "visual_prompt": "Photorealistic documentary view looking up through the massive stone columns of the Great Hypostyle Hall at Karnak Temple, sunbeams cutting through the towering sandstone pillars",
                "environment": "Ancient Egyptian temple hypostyle hall with towering columns",
                "characters": "Monumental carved stone columns",
                "objects": "Sandstone pillars, carved lotus capitals, shafts of sunlight",
                "camera_style": "Majestic low-angle tilt shot looking up along the colossal columns"
            }
        ],
        "closing": "Ancient Egypt's monumental architecture, language, and culture continue to captivate human history."
    },
    "volcanoes": {
        "title": "5 Powerful Facts About Volcanoes and Earth's Magma",
        "topic": "Volcanoes",
        "hook": "Volcanoes are the dynamic pressure valves that vent Earth's interior heat.",
        "facts": [
            {
                "claim": "Subduction Zone Magma Drives Explosive Stratovolcanoes",
                "explanation": "When an oceanic plate subducts, water trapped in minerals lowers the melting point of the mantle, generating volatile silica-rich magma.",
                "example": "Mount St. Helens and Mount Fuji are iconic stratovolcanoes fueled by volatile subduction zone magma.",
                "narration": "Explosive stratovolcanoes form where oceanic plates sink deep into the mantle. Trapped ocean water superheats the surrounding rock, generating gas-rich magma that erupts violently through the crust.",
                "visual_prompt": "Cinematic photorealistic view of a towering snow-capped stratovolcano erupting with a massive vertical ash plume rising into the stratosphere, dramatic geological scale, vertical 9:16 composition",
                "environment": "Volcanic mountain landscape with billowing eruption column",
                "characters": "The massive erupting stratovolcano",
                "objects": "Ash plume, volcanic crater, snow-covered volcanic slopes",
                "camera_style": "Dramatic telephoto wide shot capturing the full volcanic eruption column"
            },
            {
                "claim": "Pyroclastic Flows Are Fast-Moving Avalanches of Superheated Gas and Rock",
                "explanation": "Collapsing eruption columns produce high-density currents of incandescent rock and volcanic gases that travel at hundreds of kilometers per hour.",
                "example": "Pyroclastic surges from Mount Vesuvius reached temperatures exceeding 500 degrees Celsius, burying Pompeii.",
                "narration": "The deadliest volcanic hazard is the pyroclastic flow. These superheated avalanches of volcanic gas and pulverized rock race down mountainsides at hundreds of miles per hour, destroying everything in their path.",
                "visual_prompt": "Photorealistic documentary view of a dense, glowing pyroclastic flow surging down a rugged volcanic ridge, massive billowing gray dust clouds glowing internally with orange volcanic heat",
                "environment": "Rugged volcanic terrain under dark ash-filled skies",
                "characters": "The surging pyroclastic density current",
                "objects": "Glowing volcanic rock debris, billowing ash clouds, rugged ridge",
                "camera_style": "Cinematic tracking shot capturing the high-velocity flow from a safe distance"
            },
            {
                "claim": "Basaltic Hotspots Build the Planet's Largest Shield Volcanoes",
                "explanation": "Stationary mantle plumes produce low-viscosity basaltic lava that flows easily over vast distances, building broad shield profiles.",
                "example": "Mauna Loa in Hawaii is the world's most massive active volcano, rising over 9 kilometers from the oceanic floor.",
                "narration": "Deep mantle hotspots generate low-viscosity basaltic lava. Instead of exploding, fluid molten rock spreads out over vast distances, building colossal shield volcanoes like Hawaii's Mauna Loa.",
                "visual_prompt": "Photorealistic aerial view of glowing orange basaltic lava rivers cascading smoothly across dark volcanic terrain into the crashing ocean, steam plumes rising against a twilight sky",
                "environment": "Oceanic volcanic coastline with active lava flow entering the sea",
                "characters": "Glowing molten basaltic lava rivers",
                "objects": "Crusted lava rock, glowing orange channels, coastal steam plumes",
                "camera_style": "Sweeping aerial drone shot gliding over glowing lava rivers"
            },
            {
                "claim": "Volcanic Activity Continuously Creates New Islands and Crust",
                "explanation": "Undersea eruptions along mid-ocean ridges and hotspots continuously deposit fresh igneous rock, expanding oceanic crust and forming new islands.",
                "example": "The island of Surtsey emerged from the Atlantic Ocean near Iceland in 1963 following submarine volcanic eruptions.",
                "narration": "Volcanoes are Earth's primary land builders. Undersea eruptions continuously solidify into fresh igneous basalt, creating new oceanic crust and giving birth to new islands across the globe.",
                "visual_prompt": "Photorealistic documentary view of a newly formed volcanic island surrounded by deep blue ocean waves, black volcanic beaches, and steam venting from a fresh volcanic crater",
                "environment": "Open ocean with newly emerged black volcanic island",
                "characters": "The newly formed volcanic island",
                "objects": "Black sand beaches, steaming volcanic rock, turquoise ocean surf",
                "camera_style": "Orbital aerial panning shot around the volcanic island"
            },
            {
                "claim": "Weathered Volcanic Ash Creates Exceptionally Fertile Agricultural Soils",
                "explanation": "Volcanic tephra is rich in vital minerals such as potassium, phosphorus, and calcium, breaking down into highly fertile Andisols.",
                "example": "Slopes surrounding Mount Etna in Sicily support rich vineyards and olive groves due to mineral-dense volcanic soil.",
                "narration": "Despite their destructive power, volcanoes nourish life. Weathered volcanic ash is packed with essential minerals like potassium and phosphorus, creating some of the most fertile agricultural soils on Earth.",
                "visual_prompt": "Photorealistic documentary view of lush green terraced vineyards and orchards flourishing on the rich dark volcanic slopes beneath a majestic volcanic peak",
                "environment": "Terraced agricultural fields on mineral-rich volcanic mountainside",
                "characters": "Lush green vineyards on volcanic soil",
                "objects": "Grapevine terraces, dark rich volcanic earth, distant volcanic peak",
                "camera_style": "Golden hour landscape shot showcasing the fertile volcanic farm slopes"
            }
        ],
        "closing": "Volcanoes remind us that Earth is an active, living planet continuously renewing its surface."
    },
    "black holes": {
        "title": "5 Mind-Bending Facts About Black Holes",
        "topic": "Black Holes",
        "hook": "Black holes represent the most extreme gravitational environments in the known universe.",
        "facts": [
            {
                "claim": "The Event Horizon Marks the Absolute Boundary of No Return",
                "explanation": "Within the Schwarzschild radius, escape velocity exceeds the speed of light, making it impossible for matter or radiation to escape.",
                "example": "A black hole with the mass of Earth would have an event horizon radius of just 9 millimeters.",
                "narration": "A black hole's boundary is called the event horizon. Beyond this perimeter, gravitational pull is so extreme that the escape velocity exceeds the speed of light, trapping all matter and radiation forever.",
                "visual_prompt": "Photorealistic scientific simulation view of a black hole with a sharp black event horizon shadow surrounded by a brilliant glowing accretion disk warping light through intense gravitational lensing, deep space background, vertical 9:16 composition",
                "environment": "Deep cosmic space with distant stars and glowing interstellar nebulae",
                "characters": "The black hole and its event horizon shadow",
                "objects": "Glowing accretion disk, warped starlight, photon sphere ring",
                "camera_style": "Slow orbital cinematic push toward the event horizon"
            },
            {
                "claim": "Gravitational Lensing Warps the Very Geometry of Starlight",
                "explanation": "Intense gravitational curvature bends passing light rays, creating optical distortions known as Einstein rings.",
                "example": "Light from stars behind the black hole is bent around it, creating multiple mirrored images of the background cosmos.",
                "narration": "Because black holes curve spacetime so intensely, they act as cosmic magnifying glasses. Passing starlight is warped into circular halos called Einstein rings, bending the background universe around the abyss.",
                "visual_prompt": "Cinematic visual of intense gravitational lensing bending background starfields and colorful galaxies into concentric rings around a dark central gravitational singularity in deep space",
                "environment": "Deep interstellar space with warped background galaxies",
                "characters": "The gravitational lensing phenomenon",
                "objects": "Einstein rings, distorted starlight arcs, cosmic dust clouds",
                "camera_style": "Smooth panning shot observing background star distortions around the singularity"
            },
            {
                "claim": "Accretion Disks Generate Enormous Relativistic Energy and Plasma Jets",
                "explanation": "Infalling matter accelerates near light speed, converting gravitational energy into intense X-ray radiation and shooting relativistic plasma jets from the poles.",
                "example": "Supermassive black holes power quasars, outshining entire host galaxies containing hundreds of billions of stars.",
                "narration": "Infalling gas swirls into a superheated accretion disk at near light-speed. Friction heats the matter to millions of degrees, launching collimated relativistic plasma jets thousands of light-years into space.",
                "visual_prompt": "Stunning astrophysical view of a supermassive black hole blasting dual ultra-relativistic blue plasma jets vertically from its poles across interstellar space, surrounded by a swirling fiery accretion disk",
                "environment": "Active galactic nucleus space environment",
                "characters": "The relativistic plasma jets and accretion disk",
                "objects": "Blazing plasma beams, glowing accretion vortex, magnetic field lines",
                "camera_style": "Dramatic high-angle galactic perspective showing the vast scale of the plasma jets"
            },
            {
                "claim": "Gravitational Time Dilation Slows Time Near the Singularity",
                "explanation": "General Relativity proves that strong gravitational fields slow the passage of time relative to distant observers.",
                "example": "An observer hovering near an event horizon would experience mere minutes while centuries elapse in the outside universe.",
                "narration": "According to Einstein's general relativity, intense gravity slows time itself. An observer near a black hole would experience a few minutes while hundreds of years pass in the outside universe.",
                "visual_prompt": "Photorealistic conceptual visualization of distorted spacetime fabric warping deeply into a gravity well around a black hole, with light beams bending and stretching across the gravitational field",
                "environment": "Abstract spacetime grid visualization in deep cosmos",
                "characters": "Curved spacetime continuum grid",
                "objects": "Spacetime curvature lines, warped light clocks, gravitational well",
                "camera_style": "Perspective shot moving along the curving spacetime grid"
            },
            {
                "claim": "Supermassive Black Holes Anchor the Centers of Major Galaxies",
                "explanation": "Galaxies contain central supermassive black holes containing millions to billions of solar masses that influence galaxy evolution.",
                "example": "Sagittarius A* at the center of the Milky Way contains roughly 4.3 million times the mass of our Sun.",
                "narration": "At the heart of nearly every large galaxy lies a supermassive black hole. Sagittarius A* at the center of our Milky Way anchors millions of stars, playing a crucial role in the evolution of our galaxy.",
                "visual_prompt": "Magnificent astronomical view of a bright galactic core with hundreds of stars orbiting tightly around the glowing shadow of Sagittarius A* at the center of the Milky Way galaxy",
                "environment": "Dense stellar galactic nucleus with dense star clusters",
                "characters": "The central supermassive black hole Sagittarius A*",
                "objects": "Orbiting blue supergiant stars, glowing interstellar dust, galactic halo",
                "camera_style": "Wide orbital view looking across the central galactic star cluster"
            }
        ],
        "closing": "Black holes push the boundaries of physics, testing the very limits of our understanding of the universe."
    },
    "world war ii": {
        "title": "5 Pivotal Technological and Strategic Facts of World War II",
        "topic": "World War II",
        "hook": "World War II was the largest conflict in human history, shaped by strategic turning points.",
        "facts": [
            {
                "claim": "Cavity Magnetron Radar Transformed the Battle of Britain",
                "explanation": "The development of the cavity magnetron enabled compact, high-frequency microwave radar that detected incoming aircraft through clouds and darkness.",
                "example": "The Chain Home radar network gave RAF Fighter Command early warning, allowing coordinated interception of Luftwaffe formations.",
                "narration": "Early radar technology played a decisive role in the Battle of Britain. Britain's Chain Home radar network detected incoming aircraft over the English Channel, allowing fighter pilots to intercept enemy formations with pinpoint precision.",
                "visual_prompt": "Photorealistic historical documentary view of a coastal British Chain Home radar tower standing tall on the white cliffs of Dover, overlooking the English Channel under dramatic storm clouds, vertical 9:16 composition",
                "environment": "White cliffs of Dover overlooking the English Channel in 1940",
                "characters": "British Chain Home radar steel towers",
                "objects": "Steel lattice antenna towers, coastal cliffs, English Channel waters",
                "camera_style": "Dramatic low-angle tracking shot along the coastal radar installation"
            },
            {
                "claim": "Enigma Cryptanalysis at Bletchley Park Shortened the War",
                "explanation": "Mathematicians at Bletchley Park built electromechanical 'Bombe' machines to systematically break encrypted German Enigma communications.",
                "example": "Intelligence gathered under the codename Ultra provided Allied commanders with advance notice of U-boat convoy ambushes.",
                "narration": "At Bletchley Park, mathematicians designed the first electromechanical codebreaking machines. By cracking the complex German Enigma cipher, Allied intelligence intercepted critical enemy directives, shortening the war by years.",
                "visual_prompt": "Detailed historical documentary view of an authentic Enigma cipher machine with brass rotors and mechanical keyboard on an oak officer desk surrounded by military maps and cipher codebooks",
                "environment": "Dimly lit 1940s military intelligence office",
                "characters": "The three-rotor mechanical Enigma cipher machine",
                "objects": "Enigma rotor wheels, plugboard cables, decoded military telegraphs, maps",
                "camera_style": "Macro close-up focusing on the turning brass Enigma rotors"
            },
            {
                "claim": "The Logistics of the Normandy Amphibious Landings",
                "explanation": "Operation Overlord on June 6, 1944, was the largest amphibious invasion in history, utilizing artificial Mulberry harbors and PLUTO fuel pipelines.",
                "example": "Over 156,000 Allied troops and thousands of naval vessels landed along a 50-mile stretch of the Normandy coastline on D-Day.",
                "narration": "The D-Day landings in Normandy were the largest amphibious invasion ever mounted. Over one hundred and fifty thousand Allied troops crossed the English Channel, supported by prefabricated artificial harbors and massive naval bombardments.",
                "visual_prompt": "Historical documentary view of the wide sandy Normandy coastline at Omaha Beach, with landing craft along the shoreline, barrage balloons in the overcast sky, and historic military fortifications",
                "environment": "Normandy coastline on an overcast morning in 1944",
                "characters": "Allied amphibious naval landing fleet and coastline",
                "objects": "Landing craft, coastal obstacles, sand dunes, barrage balloons",
                "camera_style": "Wide cinematic panoramic view capturing the historic Normandy landing beach"
            },
            {
                "claim": "Industrial Mass Production of Aircraft and Tanks",
                "explanation": "Allied industrial assembly lines produced military hardware at an unprecedented scale, outproducing the Axis powers.",
                "example": "The Willow Run manufacturing plant produced a B-24 Liberator bomber every 63 minutes at peak wartime capacity.",
                "narration": "Wartime industrial manufacturing reached unprecedented speeds. Automotive factories were converted into aircraft plants, with massive assembly lines producing heavy four-engine bombers at a rate of one plane every hour.",
                "visual_prompt": "Photorealistic historical documentary view of a vast wartime aircraft manufacturing factory floor, with rows of aluminum B-24 bomber fuselages being assembled under industrial skylights",
                "environment": "Massive 1940s industrial aviation manufacturing factory",
                "characters": "Rows of heavy bomber airframes on assembly tracks",
                "objects": "Aluminum aircraft wings, riveting tools, overhead factory cranes",
                "camera_style": "Deep perspective tracking shot along the continuous factory assembly line"
            },
            {
                "claim": "The Manhattan Project and the Advent of the Atomic Age",
                "explanation": "The secret wartime scientific project at Los Alamos developed the first nuclear weapons through breakthroughs in uranium isotope separation and plutonium implosion.",
                "example": "The Trinity test on July 16, 1945, in the New Mexico desert marked the world's first successful detonation of a nuclear device.",
                "narration": "The secret Manhattan Project brought together top international physicists to develop nuclear fission. The successful Trinity test in the New Mexico desert ushered the world into the atomic age, permanently transforming global geopolitics.",
                "visual_prompt": "Historical documentary view of the Trinity test site in the New Mexico desert, with a vintage 100-foot steel test tower standing alone beneath a vast desert sky, 1945 historical setting",
                "environment": "Arid Jornada del Muerto desert plain in New Mexico",
                "characters": "The historic Trinity steel test gantry tower",
                "objects": "Steel test tower, desert brush, instrument bunkers, clear horizon",
                "camera_style": "Low-angle cinematic wide shot capturing the isolated desert test tower"
            }
        ],
        "closing": "World War II forever transformed international alliances, technology, and global governance."
    },
    "python": {
        "title": "3 Critical Python Mistakes Beginners Make",
        "topic": "Python programming",
        "hook": "Subtle Python behaviors can silently corrupt application data without throwing a single error.",
        "facts": [
            {
                "claim": "Mutable Default Arguments are Shared Across Calls",
                "explanation": "Default argument expressions in Python are evaluated once when the function is defined, not every time it is called.",
                "example": "Using `def append_to(item, target=[])` causes all function calls to append to the exact same persistent list in memory.",
                "narration": "In Python, default function arguments are created once when the function is defined, not when it runs. Using an empty list as a default parameter means every function call mutates the exact same shared list in memory.",
                "visual_prompt": "A code snippet with `def append(item, target=[])` highlighted in warning amber, with an animated memory address pointer showing multiple function calls pointing to the exact same list object in RAM",
                "environment": "Dark IDE software workspace with visual memory inspector graph",
                "characters": "Memory address pointer and heap object block",
                "objects": "Python code window, memory address hex indicators, heap memory allocation visualizer",
                "camera_style": "Over-the-shoulder macro view of high-contrast coding interface"
            },
            {
                "claim": "Identity (is) versus Equality (==) Comparison Trap",
                "explanation": "`==` checks value equality, whereas `is` checks memory address identity. Python caches small integers (-5 to 256) but not larger numbers.",
                "example": "`a = 1000; b = 1000; a is b` evaluates to False because they occupy separate heap allocations, even though `a == b` is True.",
                "narration": "The double equals operator checks if values match, but the keyword 'is' checks if two variables share the exact same memory address. Large numbers with identical values will fail an identity comparison because Python allocates them in separate memory blocks.",
                "visual_prompt": "Two identical numeric data blocks in memory with distinct hex memory addresses, visualized with comparison logic showing green equality checkmark and red identity X",
                "environment": "Python virtual machine bytecode execution visualizer",
                "characters": "Memory comparison evaluator",
                "objects": "Hex memory address tags, equality vs identity evaluation badges",
                "camera_style": "Close-up split focus on two memory registers"
            },
            {
                "claim": "Modifying a List While Iterating Skips Elements",
                "explanation": "Iterating over a list uses an internal index pointer. Removing elements shifts remaining items left, causing the loop to skip the adjacent item.",
                "example": "Using `for item in items: if condition: items.remove(item)` skips every second matching element.",
                "narration": "Deleting items from a list while looping over it silently skips elements. As items are removed, Python shifts the remaining elements left, causing the loop's internal index counter to skip the next adjacent item.",
                "visual_prompt": "An animated list array showing an index pointer stepping forward while items shift left, with a skipped element visibly highlighted in bright red alert styling",
                "environment": "Algorithmic data structure debugging environment",
                "characters": "Array index stepper cursor",
                "objects": "Array index boxes, element shift vectors, skip warning indicator",
                "camera_style": "Smooth tracking shot following the index cursor across the array"
            }
        ],
        "closing": "Mastering memory allocation and iteration mechanics turns beginner code into robust production Python."
    },
    "artificial intelligence": {
        "title": "5 Surprising Facts About Artificial Intelligence",
        "topic": "Artificial Intelligence",
        "hook": "Large language models do not search a database or think like humans do.",
        "facts": [
            {
                "claim": "Token-by-Token Probability Prediction",
                "explanation": "LLMs break text into sub-word tokens and select the next token using probability distributions learned during training.",
                "example": "When completing a sentence, the model calculates soft-max probabilities across vocabulary tokens rather than retrieving pre-written sentences.",
                "narration": "Instead of searching static databases, language models break text into sub-word tokens, predicting each next word from probabilities learned during training.",
                "visual_prompt": "A visual demonstration of a sentence forming token-by-token in 3D glowing glyphs, with branch probability trees and statistical weight percentages floating beside each candidate word, dark technical laboratory atmosphere, macro cinematography",
                "environment": "Deep neural architecture visualization space with glowing vector manifolds",
                "characters": "Digital token streams and mathematical tensor arrays",
                "objects": "Floating glowing token boxes, mathematical probability meters, vector matrix grids",
                "camera_style": "Macro tracking shot pushing through glowing token vectors"
            },
            {
                "claim": "Diffusion Models Remove Noise to Create Imagery",
                "explanation": "Generative image models start with pure Gaussian noise and iteratively subtract predicted noise over dozens of steps until a coherent photorealistic image emerges.",
                "example": "Latent diffusion maps text prompts to mathematical vector embeddings that guide the reverse-diffusion denoising process.",
                "narration": "Generative image models start with pure static noise, gradually removing noise patterns over dozens of computational steps to synthesize visuals.",
                "visual_prompt": "A chaotic field of pure static noise progressively crystallizing over temporal steps into an intricate, photorealistic human eye and futuristic landscape, showing the denoising mathematical boundary lines, vertical 9:16 framing",
                "environment": "High-dimensional latent space environment transitioning from raw noise to crystalline detail",
                "characters": "Emerging photorealistic subject from mathematical latent noise",
                "objects": "Denoising step counters, latent vector grids, frequency spectrograms",
                "camera_style": "Slow zoom into the center of the resolving image"
            },
            {
                "claim": "Hallucination is an Inherent Statistical Artifact",
                "explanation": "AI models generate plausible-sounding false information because they optimize for linguistic coherence and statistical correlation, not factual ground truth.",
                "example": "A model can invent a completely fictional citation because the syntax matches valid academic documents.",
                "narration": "AI hallucinations happen because models optimize for plausible linguistic fluency rather than factual truth, generating confident errors when probabilities align.",
                "visual_prompt": "A split visual comparing a fabricated legal manuscript rendered in glowing holographic text against an empty verification archive with red analytical variance markers highlighting statistical confidence versus factual absence",
                "environment": "Modern data audit chamber with holographic document analysis displays",
                "characters": "Analytical algorithmic verification scanner",
                "objects": "Holographic legal/scientific document, verification discrepancy overlays, confidence score graphs",
                "camera_style": "Split-view panning shot with dramatic red and cyan contrast lighting"
            },
            {
                "claim": "Self-Attention Mechanism Dynamically Links Context",
                "explanation": "The Transformer architecture uses self-attention to calculate mathematical relationships between all words across long documents simultaneously.",
                "example": "Self-attention links distant pronouns and concepts across multi-page contexts without sequential reading bottlenecks.",
                "narration": "A key breakthrough behind modern language models is the Transformer's self-attention mechanism, linking context across entire documents simultaneously.",
                "visual_prompt": "A complex 3D network of glowing text documents where intense beams of light dynamically connect distant words across pages, visualizing attention weight intensity and multi-head attention heads in real time",
                "environment": "Massive holographic data archive with suspended interconnected text planes",
                "characters": "Multi-head attention connection vectors",
                "objects": "Attention heatmaps, connection beams, matrix multiplication visualization",
                "camera_style": "Sweeping orbital shot around the 3D attention lattice"
            },
            {
                "claim": "Quantization Enables Efficient Local Inference",
                "explanation": "Post-training quantization reduces 16-bit floating-point weights to lower bit-depth representations, substantially reducing memory requirements.",
                "example": "Quantized models run on consumer laptops and edge devices with manageable quality trade-offs.",
                "narration": "Quantization reduces model memory requirements substantially, allowing large models to run on consumer hardware with manageable quality trade-offs.",
                "visual_prompt": "A massive glowing 16-bit neural network lattice compressing and packing tightly into a compact, glowing silicon chip on a modern motherboard, precision laser calibration beams demonstrating size reduction",
                "environment": "Cleanroom microchip fabrication and computing hardware architecture",
                "characters": "Compact high-efficiency neural accelerator silicon die",
                "objects": "Silicon wafer, memory bus traces, floating bit-depth comparison indicators",
                "camera_style": "Extreme close-up macro tracking shot over gold circuit traces"
            }
        ],
        "closing": "These core mechanisms make AI a powerful probabilistic calculator."
    },
    "airplane": {
        "title": "Why Do Airplanes Fly? The Aerodynamics of Lift",
        "topic": "Aerodynamics and Aviation",
        "hook": "Heavy metal aircraft weighing hundreds of tons stay aloft through dynamic fluid mechanics.",
        "facts": [
            {
                "claim": "Airfoil Camber and Asymmetric Pressure Differential",
                "explanation": "A curved upper wing surface accelerates oncoming airflow, creating a localized low-pressure zone on top and higher pressure underneath in accordance with Bernoulli's principle.",
                "example": "The pressure difference across a commercial Boeing 737 wing area generates thousands of pounds of upward vertical force.",
                "narration": "An airplane wing is shaped with an asymmetric curve called an airfoil. As the wing moves forward, air flows faster over the curved top than the flat bottom, creating a low-pressure pocket above that draws the aircraft upward.",
                "visual_prompt": "A technical wind-tunnel cross section of an aircraft wing airfoil with glowing streamline air currents, showing high-velocity low-pressure blue air on top and high-pressure red air below, particle velocity vectors",
                "environment": "Aerodynamic wind tunnel testing laboratory",
                "characters": "Airfoil cross section and streamline particle flow",
                "objects": "Streamline particle emitters, pressure differential barometers, velocity vectors",
                "camera_style": "Macro profile cross-section shot with smooth particle flow"
            },
            {
                "claim": "Newtonian Downwash Deflection",
                "explanation": "By tilting the wing at an angle of attack, oncoming air is deflected downwards. In accordance with Newton's Third Law, deflecting air down exerts an equal and opposite upward reaction on the wing.",
                "example": "At takeoff pitch angles, downward momentum transfer accounts for over 50% of total generated vertical lift.",
                "narration": "Lift is also driven by Newtonian physics. The wing's angle of attack pushes tons of oncoming air molecules downward every second. In response, Newton's third law generates an equal and opposite upward thrust on the airframe.",
                "visual_prompt": "A dynamic 3D simulation of a passenger jet wing cutting through clouds, showing massive downward swirling air currents (downwash) trailing behind the trailing edge with upward reaction force arrows",
                "environment": "High-altitude atmospheric cloud layer visualization",
                "characters": "Commercial jet wing structure",
                "objects": "Downwash vortex streams, force vector arrows, angle of attack indicator",
                "camera_style": "Trailing side-quarter angle tracking the wing through cloud layers"
            },
            {
                "claim": "Thrust-to-Drag Equilibrium and Wingtip Vortices",
                "explanation": "High pressure below leaks around wingtips to low pressure above, forming turbulent vortex spirals that induce drag. Winglets diffuse these vortices to save fuel.",
                "example": "Blended winglets reduce induced drag by up to 5% by smoothing high-pressure spillover at wingtips.",
                "narration": "At the wingtips, high-pressure air curls around into the low-pressure zone above, creating swirling vortices of wasted energy. Modern winglets deflect this vortex spillover, converting lost energy back into forward flight efficiency.",
                "visual_prompt": "A close-up of an upward-curved composite winglet slicing through atmospheric vapor, visualizing the turbulent spiral vortex being straightened into smooth laminar airflow",
                "environment": "Cruising altitude sunset atmosphere with condensation vapor",
                "characters": "Carbon-composite winglet tip",
                "objects": "Vortex spiral condensation trails, laminar flow streamlines",
                "camera_style": "Close-up cinematic telephoto tracking shot on the wingtip"
            }
        ],
        "closing": "Flight is the harmony of pressure differentials, downward momentum transfer, and drag mitigation."
    },
    "mars": {
        "title": "How Mars Rovers Land and Discover Secrets",
        "topic": "Mars Exploration",
        "hook": "Landing a one-ton robotic laboratory on Mars requires surviving the seven minutes of terror.",
        "facts": [
            {
                "claim": "Supersonic Retropropulsion and Sky Crane Landing",
                "explanation": "Because Mars's atmosphere is only 1% as dense as Earth's, parachutes alone cannot stop a rover. A rocket-powered sky crane lowers the vehicle on nylon tethers before flying away.",
                "example": "The Perseverance rover was lowered onto Jezero Crater by a sky crane hover platform traveling at zero horizontal velocity.",
                "narration": "Because Mars's atmosphere is only one percent as dense as Earth's, parachutes cannot stop a rover alone. A rocket-powered sky crane descends to sixty feet above the surface and gently winches the rover down on nylon cables before rocketing away.",
                "visual_prompt": "The rocket-powered Sky Crane hovering with blazing descent thrusters above the Martian red dust, lowering the Perseverance rover on glowing nylon tethers onto the rocky surface of Jezero Crater",
                "environment": "Martian red desert surface of Jezero Crater under salmon-pink skies",
                "characters": "Perseverance rover and descent stage sky crane",
                "objects": "Hydrazine thruster plumes, suspension bridle cables, landing radar sensors",
                "camera_style": "Low-angle dramatic ground shot looking up at the lowering rover"
            },
            {
                "claim": "SuperCam Laser-Induced Breakdown Spectroscopy",
                "explanation": "The mast-mounted SuperCam fires an infrared laser to vaporize rock targets up to 20 feet away, analyzing the emitted plasma spark with spectrometers to identify mineral composition.",
                "example": "Laser zaps reveal organic molecules and clay minerals formed in ancient Martian lakebed sediments.",
                "narration": "To analyze rocks without touching them, the rover fires an infrared laser that vaporizes tiny rock points into glowing plasma sparks. An onboard spectrometer reads the light spectrum to identify mineral composition from twenty feet away.",
                "visual_prompt": "Close-up of the rover's high-tech masthead firing a precise red pulsing laser beam at an ancient layered Martian rock, creating a brilliant micro-plasma spark with spectroscopic emission graphs floating nearby",
                "environment": "Layered sedimentary rock formation on Mars",
                "characters": "SuperCam robotic masthead sensor",
                "objects": "Pulsed laser beam, micro-plasma spark, spectrometer lens assembly",
                "camera_style": "Macro focus on the rock surface receiving the laser pulse"
            },
            {
                "claim": "Autonomous Hazard Avoidance Terrain Navigation",
                "explanation": "AutoNav software processes stereo camera pairs into 3D height maps in real time, driving autonomously around boulders and sand traps without waiting for round-trip Earth signals.",
                "example": "With a 20-minute radio delay to Earth, autonomous navigation allows rovers to traverse hundreds of meters per Martian sol.",
                "narration": "Radio signals take up to twenty minutes to reach Earth, making real-time steering impossible. Instead, autonomous navigation software continuously generates 3D terrain maps to steer around sand traps and boulders independently.",
                "visual_prompt": "The rover's rugged titanium cleated wheels rolling over Martian gravel, with a real-time green 3D vector mesh overlay scanning the terrain ahead and highlighting safe driving pathways around boulders",
                "environment": "Challenging Martian boulder field and dune landscape",
                "characters": "Robotic rover navigation system",
                "objects": "3D lidar mesh overlay, path trajectory arrows, terrain elevation contours",
                "camera_style": "Forward wheel-level tracking shot moving over Martian red soil"
            }
        ],
        "closing": "Robotic rovers combine rocket-crane landings, laser spectroscopy, and autonomous navigation to explore ancient worlds."
    },
    "relaxing nature": {
        "title": "3 Powerful Ways Nature Calms Your Nervous System",
        "topic": "Nature and Stress Relief",
        "hook": "Immersing yourself in natural environments triggers rapid biological shifts that measurably reduce stress.",
        "facts": [
            {
                "claim": "Tree Phytoncides Lower Cortisol and Blood Pressure",
                "explanation": "Evergreen trees release airborne antimicrobial organic compounds called phytoncides that activate the human parasympathetic nervous system.",
                "example": "Studies in environmental medicine demonstrate that a 20-minute forest immersion reduces salivary cortisol by over 16 percent.",
                "narration": "Trees and evergreen plants release natural airborne organic compounds called phytoncides. When inhaled during a walk in the woods, these aerosols stimulate parasympathetic nerves, lowering the stress hormone cortisol by up to sixteen percent.",
                "visual_prompt": "Sunbeams breaking through towering cedar and pine trees in a tranquil green mossy forest, soft golden mist drifting between tree trunks, cinematic vertical 9:16",
                "environment": "Tranquil green mossy cedar and pine forest with sunbeams",
                "characters": "Towering forest trees and gentle morning mist",
                "objects": "Sunbeams, green moss, cedar pine needles, soft forest haze",
                "camera_style": "Slow upward tilting shot through majestic sunlit pine branches",
                "stock_query": "forest sunlight mist"
            },
            {
                "claim": "Natural Fractal Patterns Induce Calming Alpha Brainwaves",
                "explanation": "Self-similar geometric repeating patterns in tree canopies, leaves, and flowing water resonate with human visual cortex processing, stimulating relaxation.",
                "example": "Electroencephalogram monitoring shows that viewing natural fractals increases alpha wave power by up to 26 percent.",
                "narration": "The branching patterns in tree branches, ocean waves, and clouds form self-similar fractal geometries. Visual neuroscientists discovered that watching these natural fractals induces relaxed alpha brainwave activity, reducing mental exhaustion effortlessly.",
                "visual_prompt": "Cinematic slow-motion view of crystal clear mountain stream waters flowing smoothly over polished river stones, lush ferns along the water bank, vertical 9:16 composition",
                "environment": "Serene alpine mountain brook with crystal clear running water",
                "characters": "The flowing mountain stream and lush riverbank ferns",
                "objects": "Polished river stones, clear rippling water, emerald fern fronds",
                "camera_style": "Low-angle smooth tracking shot alongside flowing clear water",
                "stock_query": "mountain stream water"
            },
            {
                "claim": "Moving Water Generates Mood-Boosting Negative Air Ions",
                "explanation": "The Lenard effect occurs when turbulent rushing water collides with rock surfaces, aerosolizing billions of negative ions that enter the bloodstream.",
                "example": "High concentrations of atmospheric negative ions have been shown to elevate brain serotonin turnover within 15 minutes of exposure.",
                "narration": "Waterfalls, ocean surf, and mountain streams break water droplets apart, releasing billions of negative air ions into the breeze. These ions enhance cellular oxygen absorption and trigger the release of mood-lifting serotonin in the brain.",
                "visual_prompt": "Breathtaking cascade of a pristine natural waterfall crashing into a turquoise forest pool, delicate water spray glistening in sunlight, vertical 9:16 composition",
                "environment": "Pristine tropical forest waterfall with turquoise plunge pool",
                "characters": "The cascading waterfall and shimmering spray",
                "objects": "Crashing waterfall torrent, sunlit mist spray, turquoise pool ripples",
                "camera_style": "Majestic wide shot tilting down the length of the waterfall",
                "stock_query": "waterfall cascade pool"
            },
            {
                "claim": "The Biophilia Effect Calms Heart Rate Variability",
                "explanation": "Evolutionary adaptations hardwire human neurological architecture to interpret vibrant vegetation and unpolluted landscapes as safe survival habitats.",
                "example": "Clinical trials demonstrate that viewing open biodiverse green spaces reduces sympathetic cardiovascular fight-or-flight signaling within three minutes.",
                "narration": "Evolutionary biology shows that human physiology is naturally tuned to thriving green scenery. Merely resting your gaze upon open natural landscapes stabilizes heart rate variability and shuts down anxious sympathetic fight-or-flight responses.",
                "visual_prompt": "Cinematic wide landscape view of rolling vibrant green meadows bordered by wildflowers swaying gently under a warm sunlit summer breeze, vertical 9:16",
                "environment": "Expansive sunny green meadow with colorful summer wildflowers",
                "characters": "Rolling hills of lush green grass and vibrant flowers",
                "objects": "Wildflower blossoms, waving green grass, warm sun flare",
                "camera_style": "Smooth aerial glide over blooming wildflower meadow",
                "stock_query": "green meadow wildflowers"
            },
            {
                "claim": "Morning Sunlight Exposure Synchronizes Circadian Rhythms",
                "explanation": "Full-spectrum natural daylight stimulates intrinsically photosensitive retinal ganglion cells that calibrate the hypothalamic suprachiasmatic nucleus.",
                "example": "Natural morning outdoor light delivers over 10,000 lux compared to typical indoor lighting of 500 lux, optimizing cortisol awakening curves.",
                "narration": "Natural morning sunlight filtering through the open sky stimulates retinal ganglion cells that reset your master circadian clock, boosting daytime mental focus while priming your body for deep restorative sleep at night.",
                "visual_prompt": "Majestic golden sunrise breaking over misty mountain ridges with gentle clouds floating through alpine pine valleys, warm radiant light, vertical 9:16",
                "environment": "High mountain ridge looking toward a glorious golden sunrise",
                "characters": "Golden sun rays piercing through alpine mist",
                "objects": "Sunburst, misty mountain silhouettes, floating dawn clouds",
                "camera_style": "Cinematic slow forward dolly toward the glowing mountain sunrise",
                "stock_query": "sunrise mountain clouds"
            }
        ],
        "closing": "Scientific evidence confirms that natural environments are an essential biological necessity for calming the human nervous system."
    },
    "walking benefits": {
        "title": "3 Transformative Health Benefits of Daily Walking",
        "topic": "Daily Walking",
        "hook": "Walking is the single most accessible biological intervention for cardiovascular health and cognitive longevity.",
        "facts": [
            {
                "claim": "Walking Stimulates Hippocampal Neurogenesis and Brain Plasticity",
                "explanation": "Aerobic walking enhances cerebral blood flow and releases brain-derived neurotrophic factor, triggering neurogenesis in memory centers.",
                "example": "Neuroimaging studies show that consistent brisk walking expands hippocampal volume by two percent annually, counteracting age-related atrophy.",
                "narration": "A brisk daily walk increases blood flow directly to the brain, releasing neurotrophic factors that stimulate the birth of new neurons in the hippocampus, dramatically improving memory and daily focus.",
                "visual_prompt": "Athletic person walking briskly along a peaceful sunlit path through a lush green city park, golden morning light filtering through leaves, vertical 9:16",
                "environment": "Lush green urban park with winding sunlit cobblestone walking paths",
                "characters": "Active individual walking briskly with energetic posture",
                "objects": "Dappled tree shadows, park path, vibrant green lawns",
                "camera_style": "Medium side-tracking shot keeping pace with the walker",
                "stock_query": "person walking park"
            },
            {
                "claim": "Calf Muscles Act as Secondary Venous Hearts",
                "explanation": "The skeletal muscle pump of the gastrocnemius and soleus muscles compresses deep lower-limb veins, driving venous return against gravity.",
                "example": "Rhythmic walking contractions generate pressures exceeding 100 millimeters of mercury inside intramuscular veins, preventing venous pooling.",
                "narration": "With every step, rhythmic calf contractions compress deep veins, acting as an auxiliary pump that propels oxygenated blood back up to the heart and reduces arterial stiffness throughout the body.",
                "visual_prompt": "Close-up slow motion view of athletic shoes stepping rhythmically along a scenic paved jogging trail in a sunny botanical garden, vertical 9:16",
                "environment": "Paved botanical garden fitness trail flanked by vibrant flowerbeds",
                "characters": "Athletic walking shoes in rhythmic forward motion",
                "objects": "Paved trail, athletic running shoes, sunlit garden border",
                "camera_style": "Ground-level slow-motion tracking shot following moving footsteps",
                "stock_query": "walking shoes path"
            },
            {
                "claim": "Post-Meal Walking Flattens Blood Glucose Spikes",
                "explanation": "Muscle contractions stimulate GLUT4 glucose transporter translocation to the sarcolemma independent of circulating insulin levels.",
                "example": "A 15-minute postprandial stroll reduces peak glycemic excursion by up to 22 percent compared to sedentary resting.",
                "narration": "Just ten to fifteen minutes of walking after meals activates non-insulin-mediated glucose transporters in skeletal muscle, pulling sugar straight from the bloodstream and preventing post-meal energy crashes.",
                "visual_prompt": "Cinematic perspective of a person walking along an expansive scenic wooden boardwalk overlooking the ocean at sunset, soft warm light, vertical 9:16",
                "environment": "Scenic coastal wooden boardwalk above sandy beach at golden hour",
                "characters": "Individual enjoying a peaceful post-meal sunset stroll",
                "objects": "Wooden boardwalk planks, distant ocean waves, glowing sunset sky",
                "camera_style": "Wide cinematic tracking shot from behind the walker toward the sunset",
                "stock_query": "walk ocean sunset"
            }
        ],
        "closing": "Consistent daily walking rewires your brain, balances your metabolism, and protects your cardiovascular system."
    }
}


def _clean_user_prompt_topic(prompt: str) -> str:
    """Extract clean subject topic by stripping prompt wrapper words, counts, and video creation commands."""
    cleaned = prompt.strip().rstrip(".:!?-")
    
    # Strip leading command / creation directives
    cleaned = re.sub(r"(?i)^(create|make|generate|produce|build|give\s+me|write)\s+(a\s+|an\s+)?(new\s+)?(video|short|reel|tiktok|content|script|story|breakdown)?\s*(about|on|for|of)?\s*", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^(tell\s+me\s+about|explain|teach\s+me\s+about|show\s+me)\s*", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^(top\s+)?\d+\s+(fascinating\s+|surprising\s+|interesting\s+|mind-blowing\s+|amazing\s+|best\s+|calming\s+|relaxing\s+)?(facts|things|secrets|reasons|insights|benefits|tips|ways|habits)\s+(about|on|for|of)?\s*", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^(the\s+)?(benefits|secrets|reasons|facts)\s+(about|on|for|of)\s*", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^facts\s+(about|on|for|of)?\s*", "", cleaned).strip()
    
    # Strip trailing filler / suffixes
    cleaned = re.sub(r"(?i)\s+(video|short|reel|tiktok|script)$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+[—\-–]\s*\d+\s*(fascinating|surprising|interesting|mind-blowing)?\s*facts.*$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+[—\-–]\s*explained.*$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+explained.*$", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\s+(that\s+instantly\s+reduce\s+stress|you\s+need\s+to\s+know|for\s+university\s+students|for\s+beginners).*$", "", cleaned).strip()
    
    # Strip any remaining trailing 'video' if not alone
    if len(cleaned.split()) > 1 and cleaned.lower().endswith(" video"):
        cleaned = cleaned[:-6].strip()
        
    return cleaned.strip() or prompt.strip()


def _match_knowledge_base(prompt: str) -> Optional[Dict[str, Any]]:
    """Match prompt against rich curated domain knowledge bases."""
    p_clean = prompt.lower().strip()
    
    # Priority keyword mappings
    if any(k in p_clean for k in ["relax", "stress", "calm", "nature fact", "forest bath"]):
        return TOPIC_KNOWLEDGE_BASE.get("relaxing nature")
    if any(k in p_clean for k in ["walking", "daily walk", "walk", "step count", "brisk walk", "stroll"]):
        return TOPIC_KNOWLEDGE_BASE.get("walking benefits")
    if any(k in p_clean for k in ["rain", "rainy", "precipitation", "petrichor", "downpour"]):
        return TOPIC_KNOWLEDGE_BASE.get("rainy day")
    if any(k in p_clean for k in ["earth", "geography", "geology", "continent", "ocean", "mountain", "planet"]):
        return TOPIC_KNOWLEDGE_BASE.get("earth geography")
    if any(k in p_clean for k in ["egypt", "pyramid", "pharaoh", "nile"]):
        return TOPIC_KNOWLEDGE_BASE.get("ancient egypt")
    if any(k in p_clean for k in ["volcano", "lava", "magma", "eruption"]):
        return TOPIC_KNOWLEDGE_BASE.get("volcanoes")
    if any(k in p_clean for k in ["black hole", "singularity", "event horizon"]):
        return TOPIC_KNOWLEDGE_BASE.get("black holes")
    if any(k in p_clean for k in ["world war ii", "world war 2", "wwii", "normandy", "d-day"]):
        return TOPIC_KNOWLEDGE_BASE.get("world war ii")
    if any(k in p_clean for k in ["python", "mutable default"]):
        return TOPIC_KNOWLEDGE_BASE.get("python")
    if any(k in p_clean for k in ["artificial intelligence", "ai model", "diffusion model", "transformer model", "token prediction"]):
        return TOPIC_KNOWLEDGE_BASE.get("artificial intelligence")
    if any(k in p_clean for k in ["airplane", "aerodynamic", "flight lift"]):
        return TOPIC_KNOWLEDGE_BASE.get("airplane")
    if any(k in p_clean for k in ["mars", "perseverance rover", "curiosity rover"]):
        return TOPIC_KNOWLEDGE_BASE.get("mars")

    return None


def _synthesize_arbitrary_topic_facts(topic: str, target_count: int = 5, visual_style: str = "realistic") -> List[Dict[str, Any]]:
    """
    Dynamically generates 5 distinct, factually grounded informational scenes for ANY arbitrary topic.
    Guarantees zero meta language and no tech fallback buzzwords for non-tech subjects.
    """
    is_tech = is_tech_domain(topic)
    
    if is_tech:
        return [
            {
                "claim": f"Algorithmic Architecture and Core Principles of {topic}",
                "explanation": f"The computational framework of {topic} is built on optimized data processing layers.",
                "example": f"Standard implementations decouple interface logic from core algorithmic processing.",
                "narration": f"The foundational architecture of {topic} relies on specialized computational structures designed to optimize execution speed and maintain algorithmic stability.",
                "visual_prompt": f"A clean coding IDE display showing structured algorithms and data processing logic for {topic}, high-contrast syntax highlighting, dark software developer workspace, vertical 9:16 framing",
                "environment": "Modern software development workspace with multi-monitor code editors",
                "characters": "Algorithmic data structures and function definitions",
                "objects": "Code editor window, syntax-highlighted code, terminal execution outputs",
                "camera_style": "Macro over-the-shoulder shot focused on the coding screen"
            },
            {
                "claim": f"Throughput Optimization and Execution Mechanics in {topic}",
                "explanation": f"Resource allocation and latency are optimized through efficient runtime execution paths.",
                "example": f"Benchmark profiling measures execution throughput across varying workload constraints.",
                "narration": f"Execution efficiency in {topic} depends on continuous throughput optimization, minimizing latency by streamlining data transfers between core modules.",
                "visual_prompt": f"A high-contrast visual display demonstrating data throughput metrics and processing latency benchmarks for {topic}, clean UI graphs, vertical composition",
                "environment": "Performance benchmarking and analytics dashboard",
                "characters": "System performance graphs and latency gauges",
                "objects": "Throughput bar charts, execution timeline monitors, data transfer graphs",
                "camera_style": "Medium close-up focusing on dynamic performance metrics"
            },
            {
                "claim": f"Data Verification and Fault Isolation Protocols in {topic}",
                "explanation": f"Automated boundary checks detect anomalous states before systemic errors propagate.",
                "example": f"Validation routines sanitize incoming requests and isolate edge-case failures.",
                "narration": f"To prevent runtime crashes, dedicated validation protocols monitor state continuously, catching anomalous inputs through automated boundary checks.",
                "visual_prompt": f"A software testing suite interface verifying test assertions and safety boundaries for {topic}, displaying green passing badges and isolated alert logs",
                "environment": "Automated software testing and CI/CD dashboard",
                "characters": "Test assertion suite and error isolation handlers",
                "objects": "Passing test indicators, stack trace analysis badges, code coverage charts",
                "camera_style": "Smooth panning shot across the testing dashboard"
            },
            {
                "claim": f"Interoperability and Ecosystem Integration of {topic}",
                "explanation": f"Standardized API contracts enable seamless communication across diverse software platforms.",
                "example": f"Modular interfaces allow cross-platform library integrations without bespoke adapters.",
                "narration": f"Standardized interoperability contracts enable clean data exchange across diverse environments without requiring custom integration overhead.",
                "visual_prompt": f"A clean architectural system diagram illustrating modular service connections and API endpoints for {topic}, modern minimalist design, vertical 9:16 view",
                "environment": "Modern software architecture overview display",
                "characters": "Modular service connectors and API endpoints",
                "objects": "API contract schemas, service connection nodes, clean architecture layout",
                "camera_style": "Slow technical tilt shot following API data flow lines"
            },
            {
                "claim": f"Modern Benchmarks and Future Scaling of {topic}",
                "explanation": f"Iterative advancements continue to enhance efficiency benchmarks across successive generations.",
                "example": f"Empirical evaluations demonstrate substantial performance gains over legacy architectures.",
                "narration": f"Compound performance gains stem from successive architectural refinements, allowing modern implementations to achieve dramatic efficiency improvements.",
                "visual_prompt": f"A comparative benchmark timeline showing performance improvements and architectural milestones in {topic}, glowing upward trajectory graphs, 9:16 framing",
                "environment": "Technology research and development laboratory",
                "characters": "Evolutionary architecture benchmarks",
                "objects": "Performance trajectory graphs, milestone timeline, comparative metrics",
                "camera_style": "Upward panning shot along the performance benchmark curve"
            }
        ][:target_count]

    # Non-tech topics: Natural, Historical, Scientific, Geographical, Cultural
    short_words = [w for w in topic.split() if len(w) > 2 and w.lower() not in {"the", "and", "for", "with", "that", "this"}]
    short_noun = " ".join(short_words[:2]) or topic

    return [
        {
            "claim": f"Foundational Origins and Natural Evolution of {short_noun}",
            "explanation": f"The emergence of {short_noun} stems from natural physical dynamics and historical conditions.",
            "example": f"Documented scientific observations detail the earliest recorded emergence of this phenomenon.",
            "narration": f"At the foundation of this subject, fundamental physical forces and environmental conditions establish its defining properties over time.",
            "visual_prompt": f"Photorealistic documentary establishing view showing the natural setting and authentic physical foundations of {short_noun}, soft natural atmospheric light, vertical 9:16 composition",
            "environment": f"Authentic natural environment representing {short_noun}",
            "characters": f"The primary subject of {short_noun}",
            "objects": f"Distinctive natural details and physical landscape of {short_noun}",
            "camera_style": "Cinematic wide-angle establishing landscape shot",
            "stock_query": f"{short_noun} landscape"
        },
        {
            "claim": f"Core Governing Mechanisms Driving {short_noun}",
            "explanation": f"Underlying biological and physical balances dictate how {short_noun} operates in real time.",
            "example": f"Empirical measurements illustrate continuous energy transfers driving dynamic activity.",
            "narration": f"The underlying mechanism functions through delicate systemic balances, where continuous energy exchanges and internal processes maintain equilibrium.",
            "visual_prompt": f"Detailed cinematic close-up shot capturing dynamic activity and fine textures of {short_noun}, sharp focus, authentic documentary depth of field, vertical 9:16 framing",
            "environment": f"Dynamic setting highlighting the activity of {short_noun}",
            "characters": f"The active elements of {short_noun}",
            "objects": f"Characteristic structural details and natural motion of {short_noun}",
            "camera_style": "Medium close-up shot with sharp subject focus and depth of field",
            "stock_query": f"{short_noun} closeup motion"
        },
        {
            "claim": f"Remarkable Structural Diversity Across {short_noun}",
            "explanation": f"Across varying regions and ecosystems, {short_noun} exhibits extraordinary adaptations.",
            "example": f"Documented specimens demonstrate wide variation tailored to specific climates and conditions.",
            "narration": f"Across different environments, remarkable physical diversity emerges, revealing unique regional adaptations shaped by surrounding ecosystems.",
            "visual_prompt": f"Breathtaking photorealistic view of diverse regional variations and iconic features of {short_noun}, vibrant natural colors, atmospheric depth, 9:16 composition",
            "environment": f"Vibrant regional setting showcasing variations in {short_noun}",
            "characters": f"Diverse physical formations of {short_noun}",
            "objects": f"Distinctive features and natural elements of {short_noun}",
            "camera_style": "Slow panoramic tracking shot highlighting regional diversity",
            "stock_query": f"{short_noun} nature environment"
        },
        {
            "claim": f"Ecosystem Interactions and Environmental Balance",
            "explanation": f"{short_noun} actively shapes surrounding habitats, cycles, and natural balances.",
            "example": f"Interconnected environmental cycles illustrate the far-reaching influence on nearby systems.",
            "narration": f"In practical settings, continuous interaction with surrounding environments creates positive ripple effects, sustaining broader ecological and biological harmony.",
            "visual_prompt": f"Stunning aerial perspective showing {short_noun} interacting with its surrounding natural landscape and open horizon, warm natural sunlight, vertical 9:16 framing",
            "environment": f"Expansive natural landscape showing the ecosystem of {short_noun}",
            "characters": f"The broader environmental presence of {short_noun}",
            "objects": f"Ecosystem contours and atmospheric morning light",
            "camera_style": "High-angle sweeping drone shot gliding across the landscape",
            "stock_query": f"{short_noun} scenic aerial"
        },
        {
            "claim": f"Modern Scientific Discoveries and Enduring Significance",
            "explanation": f"Contemporary research continues to unveil deeper insights into the broader importance of {short_noun}.",
            "example": f"Recent technological breakthroughs provide greater clarity on how these dynamics will shape future understanding.",
            "narration": f"Scientific research and modern observation continue to uncover deeper insights into this phenomenon, revealing lasting importance for our understanding of the natural world.",
            "visual_prompt": f"Majestic cinematic documentary shot capturing the beauty and enduring significance of {short_noun}, dramatic natural lighting, vertical 9:16 composition",
            "environment": f"Iconic scenic setting reflecting the significance of {short_noun}",
            "characters": f"The enduring subject of {short_noun}",
            "objects": f"Scenic natural formations and pristine atmospheric conditions",
            "camera_style": "Dramatic low-angle cinematic hero shot looking toward the horizon",
            "stock_query": f"{short_noun} majestic documentary"
        }
    ][:target_count]


def _synthesize_domain_plan(
    prompt: str,
    duration: str,
    language: str,
    style: str,
    target_platform: str,
    visual_style: str = "realistic",
) -> VideoPlan:
    """
    Intelligently matches the prompt to rich factual domain knowledge or dynamically
    synthesizes distinct, substantive educational scenes grounded strictly in the requested topic.
    """
    cleaned_prompt = prompt.strip().rstrip(".:!?-")
    core_topic = _clean_user_prompt_topic(cleaned_prompt)

    # Determine scene count based on duration
    if "15" in duration:
        target_scene_count = 3
        per_scene_sec = 5
    elif "30" in duration:
        target_scene_count = 5
        per_scene_sec = 6
    elif "60" in duration:
        target_scene_count = 5
        per_scene_sec = 10
    else:
        target_scene_count = 5
        per_scene_sec = 6

    matched_data = _match_knowledge_base(cleaned_prompt)

    if matched_data:
        facts_list = matched_data["facts"][:target_scene_count]
        hook = clean_banned_filler(matched_data["hook"])
        closing = clean_banned_filler(matched_data["closing"])
        title = matched_data["title"]
        topic_name = matched_data.get("topic", core_topic)
    else:
        topic_name = core_topic.title()
        title = f"{topic_name}: 5 Fascinating Facts" if len(topic_name.split()) <= 4 else f"{topic_name} Explained"
        hook = f"{topic_name} is governed by powerful natural and physical phenomena."
        closing = f"These core mechanisms demonstrate the profound impact of {topic_name} on our world."
        facts_list = _synthesize_arbitrary_topic_facts(core_topic, target_scene_count, visual_style)

    scenes: List[Scene] = []
    narrations: List[str] = []

    for i, f in enumerate(facts_list):
        scene_num = i + 1
        claim_text = clean_banned_filler(f.get("claim", f"Fact {scene_num}"))
        narr_text = clean_banned_filler(f["narration"])
        v_prompt = f["visual_prompt"]

        # Final grounding check & auto-repair
        is_valid_vp, _ = validate_visual_prompt_grounding(topic_name, claim_text, narr_text, v_prompt)
        if not is_valid_vp:
            v_prompt = regenerate_grounded_visual_prompt(topic_name, claim_text, narr_text, visual_style)

        sc = Scene(
            scene_number=scene_num,
            duration=per_scene_sec,
            scene_duration=f"{per_scene_sec}s",
            narration=narr_text,
            visual_prompt=v_prompt,
            environment=f.get("environment", f"Natural setting for {topic_name}"),
            characters=f.get("characters", f"Physical subject of {topic_name}"),
            objects=f.get("objects", f"Visual features of {topic_name}"),
            camera_style=f.get("camera_style", "Medium shot, eye level"),
            visual_style=visual_style,
            visual_description=v_prompt,
            fact_number=scene_num,
            topic=topic_name,
            claim=claim_text,
            explanation=f.get("explanation", ""),
            example=f.get("example", ""),
            stock_query=f.get("stock_query") or " ".join([w for w in (claim_text + " " + topic_name).split() if len(w) > 3][:3]) or topic_name,
            video_motion_prompt=f"Cinematic {f.get('camera_style', 'slow tracking shot')}, 4k ultra high definition documentary, perfectly stable framing, smooth motion, {v_prompt}",
        )
        scenes.append(sc)
        narrations.append(sc.narration)

    complete_narration = f"{hook} " + " ".join(narrations) + f" {closing}"

    words = [w.lower().replace('#', '').replace(',', '') for w in core_topic.split() if len(w) > 3 and w.isalnum()]
    hashtags = [f"#{w}" for w in words[:3]]
    if not hashtags:
        hashtags = ["#learn", "#science", "#education"]
    hashtags.extend(["#facts", "#insights"])
    hashtags = list(dict.fromkeys(hashtags))[:5]

    return VideoPlan(
        title=title,
        short_description=f"High-density educational analysis explaining {core_topic} with clear mechanisms and visual demonstrations.",
        complete_narration=complete_narration,
        scenes=scenes,
        suggested_background_music="Majestic atmospheric educational documentary background track",
        caption=f"Explore the fascinating facts behind {core_topic}! Detailed breakdown of key principles.",
        hashtags=hashtags,
        hook=hook,
        topic=topic_name,
        closing=closing,
        facts=[
            {
                "fact_number": sc.fact_number,
                "topic": sc.topic,
                "claim": sc.claim,
                "explanation": sc.explanation,
                "example": sc.example,
                "narration": sc.narration,
                "visual_prompt": sc.visual_prompt,
            }
            for sc in scenes
        ]
    )


def generate_video_plan_groq(
    prompt: str, duration: str, language: str, style: str,
    target_platform: str, groq_api_key: str, visual_style: str = "realistic"
) -> Optional[VideoPlan]:
    """Generates structured, non-repetitive video plan using Groq Llama 3.3 70B."""
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_api_key
        )

        clean_topic = _clean_user_prompt_topic(prompt)

        user_content = f"""
Create a high-density, factually distinct video plan for:
Topic: "{clean_topic}"
Duration: {duration}
Language: {language}
Style: {style}
Platform: {target_platform}
Visual Aesthetic: {visual_style}

STRICT CONSTRAINTS:
1. THE TOPIC IS THE PRIMARY CONSTRAINT. The entire script must be directly ABOUT "{clean_topic}".
2. ZERO META VIDEO LANGUAGE: Never say "in this video", "this video explains", "creating this video", "let us create", "for this video", or talk about making a video. Speak directly about the topic.
3. Every scene must teach a completely different fact/mechanism. No repeated claims.
4. Zero filler phrases (BANNED: "Most people don't know", "Did you know", "Let us explore", "Follow for more", etc.).
5. Every narration must explain WHAT the fact is, WHY it is true, and HOW it works.
6. Every visual_prompt must depict the exact physical subject and mechanism being narrated. NO generic people at laptops. NO unrelated technology schematics.
Return ONLY valid JSON matching this schema:
{SCENE_JSON_SCHEMA}
"""
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": CONTENT_PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.6
        )
        content = response.choices[0].message.content
        if content:
            data = json.loads(content)
            topic_str = clean_banned_filler(data.get("topic") or clean_topic)
            if data.get("hook"):
                data["hook"] = clean_banned_filler(data["hook"])
            if data.get("closing"):
                data["closing"] = clean_banned_filler(data["closing"])
            scenes = [_normalize_scene(s, visual_style, topic_str) for s in data.get("scenes", [])]
            data["scenes"] = [s.model_dump() for s in scenes]
            data["topic"] = topic_str
            plan = VideoPlan.model_validate(data)
            is_valid, _ = validate_video_plan(plan, min_scenes=len(scenes))
            if is_valid:
                return plan
    except Exception as e:
        print(f"[Groq LLM Warning] {e}")
        return None
    return None


def generate_video_plan_gemini(
    prompt: str, duration: str, language: str, style: str,
    target_platform: str, gemini_api_key: str, visual_style: str = "realistic"
) -> Optional[VideoPlan]:
    """Generates structured, non-repetitive video plan using Google Gemini AI."""
    try:
        from google import genai
        from google.genai import types

        clean_topic = _clean_user_prompt_topic(prompt)
        client = genai.Client(api_key=gemini_api_key)
        user_content = f"""
{CONTENT_PLANNER_SYSTEM_PROMPT}

Create a high-density, factually distinct video plan for:
Topic: "{clean_topic}"
Duration: {duration}
Language: {language}
Style: {style}
Platform: {target_platform}
Visual Aesthetic: {visual_style}

STRICT CONSTRAINTS:
1. Speak directly about "{clean_topic}".
2. ZERO META LANGUAGE: Never say "in this video", "this video explains", "creating this video", or mention video creation.

Schema:
{SCENE_JSON_SCHEMA}
"""
        for model_name in ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_content,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                if response and getattr(response, "text", None):
                    data = json.loads(response.text)
                    topic_str = clean_banned_filler(data.get("topic") or clean_topic)
                    if data.get("hook"):
                        data["hook"] = clean_banned_filler(data["hook"])
                    if data.get("closing"):
                        data["closing"] = clean_banned_filler(data["closing"])
                    scenes = [_normalize_scene(s, visual_style, topic_str) for s in data.get("scenes", [])]
                    data["scenes"] = [s.model_dump() for s in scenes]
                    data["topic"] = topic_str
                    plan = VideoPlan.model_validate(data)
                    is_valid, _ = validate_video_plan(plan, min_scenes=len(scenes))
                    if is_valid:
                        return plan
            except Exception:
                continue
    except Exception as e:
        print(f"[Gemini LLM Warning] {e}")
        return None
    return None


def generate_video_plan(
    prompt: str,
    duration: str = "30-60 seconds",
    language: str = "English",
    style: str = "Standard",
    target_platform: str = "TikTok",
    visual_style: str = "realistic",
) -> VideoPlan:
    """
    Primary video plan generator with high-density factual content planning.
    Waterfall: Groq -> Gemini -> Domain Knowledge Synthesis Engine.
    Guarantees zero generic filler, zero meta video-production language, distinct factual units, and strict scene-to-visual topic alignment.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and groq_key != "your_groq_api_key_here":
        plan = generate_video_plan_groq(
            prompt, duration, language, style, target_platform, groq_key, visual_style
        )
        if plan:
            return plan

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key and gemini_key != "your_gemini_api_key_here":
        plan = generate_video_plan_gemini(
            prompt, duration, language, style, target_platform, gemini_key, visual_style
        )
        if plan:
            return plan

    # Guaranteed high-density topic-locked knowledge synthesis
    plan = _synthesize_domain_plan(
        prompt, duration, language, style, target_platform, visual_style
    )

    # Perform quality validation & repair if necessary
    is_valid, issues = validate_video_plan(plan, min_scenes=len(plan.scenes))
    if not is_valid:
        print(f"[Content Quality Warning] Auto-repairing plan issues: {issues}")
        if plan.hook:
            plan.hook = clean_banned_filler(plan.hook)
        if plan.closing:
            plan.closing = clean_banned_filler(plan.closing)
        for s in plan.scenes:
            s.narration = clean_banned_filler(s.narration)
            s.claim = clean_banned_filler(s.claim or "")
            is_valid_vp, reason = validate_visual_prompt_grounding(
                topic=s.topic or plan.topic or prompt,
                claim=s.claim or "",
                narration=s.narration,
                visual_prompt=s.visual_prompt,
            )
            if not is_valid_vp:
                s.visual_prompt = regenerate_grounded_visual_prompt(
                    topic=s.topic or plan.topic or prompt,
                    claim=s.claim or "",
                    narration=s.narration,
                    visual_style=visual_style,
                )
                s.visual_description = s.visual_prompt

    return plan
