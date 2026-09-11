"""
Recipe extraction (PRD §4.1)
==============================
Real pipeline once GEMINI_API_KEY is configured:
  1. Validate the URL is actually a YouTube video (InvalidRecipeUrlError if not)
  2. Fetch real metadata via YouTube's oEmbed endpoint (free, no key)
  3. Fetch the real transcript via youtube-transcript-api (free, no key)
  4. Ask Gemini whether this is actually a recipe, and if so extract it
     (NotARecipeError if Gemini says it isn't)

Falls back to the old hardcoded stub if no GEMINI_API_KEY is set, so local
preview keeps working without requiring a key up front — but URL format is
always validated either way.
"""

from __future__ import annotations

import asyncio
import json
import re

import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import CouldNotRetrieveTranscript

from app.core.config import settings
from app.core.logger import logger
from app.schemas.recipe import ExtractedRecipe, Ingredient, LLMIngredientExtractionOutput, RecipeMetadata

YOUTUBE_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
)

GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class InvalidRecipeUrlError(ValueError):
    """Raised when the submitted URL isn't a YouTube video at all."""


class NotARecipeError(ValueError):
    """Raised when the video is a valid YouTube URL but isn't a recipe."""


def detect_platform(url: str) -> str:
    if "tiktok" in url:
        return "tiktok"
    if "instagram" in url:
        return "instagram"
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    return "unknown"


def extract_video_id(url: str) -> str | None:
    match = YOUTUBE_URL_RE.search(url)
    return match.group(1) if match else None


def is_valid_youtube_url(url: str) -> bool:
    return extract_video_id(url) is not None


async def _fetch_oembed_metadata(url: str) -> dict | None:
    """Real video title/author/thumbnail — free, no API key required."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": url, "format": "json"},
            )
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception as e:
        logger.warning(f"[EXTRACTOR] oEmbed lookup failed: {e}")
        return None


def _fetch_transcript_sync(video_id: str) -> str | None:
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        return " ".join(s["text"] for s in segments)
    except CouldNotRetrieveTranscript:
        return None
    except Exception as e:
        logger.warning(f"[EXTRACTOR] Transcript fetch failed for {video_id}: {e}")
        return None


async def _fetch_transcript(video_id: str) -> str | None:
    return await asyncio.to_thread(_fetch_transcript_sync, video_id)


EXTRACTION_PROMPT = """You are a recipe extraction assistant for PrepLink, a nutrition app for parents.
You are given content from a YouTube video (its transcript, or failing that its title/description).

First decide: is this video actually showing/describing a food recipe? If it is NOT a recipe \
(e.g. it's about something unrelated to cooking), respond with exactly:
{"is_recipe": false}

If it IS a recipe, extract it as JSON matching exactly this shape:
{
  "is_recipe": true,
  "title": "string",
  "servings": integer,
  "confidence": number between 0 and 1 (how complete/certain this extraction is),
  "ingredients": [{"name": "string", "quantity": number, "unit": "string"}],
  "steps": ["string", ...]
}

Output ONLY the JSON object. No markdown fences, no commentary.

VIDEO TITLE: {title}

CONTENT:
{content}
"""


async def _call_gemini_extraction(content: str, title: str) -> dict:
    prompt = EXTRACTION_PROMPT.format(title=title or "(unknown)", content=content[:12000])
    url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


async def extract_recipe(url: str) -> ExtractedRecipe:
    if detect_platform(url) != "youtube" or not is_valid_youtube_url(url):
        raise InvalidRecipeUrlError("This URL doesn't look like a YouTube video.")

    video_id = extract_video_id(url)
    oembed = await _fetch_oembed_metadata(url)
    real_title = oembed.get("title") if oembed else None

    if not settings.GEMINI_API_KEY:
        # No key configured yet — keep the old stub so local preview still
        # works, but the URL format check above is real either way.
        return ExtractedRecipe(
            metadata=RecipeMetadata(title=real_title or "Stub Recipe from youtube", servings=4, source_url=url),
            ingredients=[
                Ingredient(name="flour", quantity=2, unit="cup"),
                Ingredient(name="egg", quantity=2, unit="whole"),
                Ingredient(name="milk", quantity=1, unit="cup"),
            ],
            steps=["Mix dry ingredients.", "Whisk in eggs and milk.", "Cook until golden."],
            confidence=0.0,
            extraction_method="stub_no_gemini_key",
        )

    transcript = await _fetch_transcript(video_id)
    content = transcript or (oembed.get("title", "") if oembed else "")
    if not content:
        raise NotARecipeError("Could not fetch any content from this video (no transcript, no metadata).")

    result = await _call_gemini_extraction(content, real_title)

    if not result.get("is_recipe", False):
        label = real_title or url
        raise NotARecipeError(f'"{label}" doesn\'t appear to be a recipe.')

    return ExtractedRecipe(
        metadata=RecipeMetadata(title=result["title"], servings=result.get("servings", 4), source_url=url),
        ingredients=[Ingredient(**i) for i in result.get("ingredients", [])],
        steps=result.get("steps", []),
        confidence=float(result.get("confidence", 0.6)),
        extraction_method="gemini_transcript" if transcript else "gemini_title_only",
    )


async def assemble_recipe(
    llm_out: LLMIngredientExtractionOutput,
    url: str,
    platform: str,
    source: str,
    confidence: float,
) -> ExtractedRecipe:
    return ExtractedRecipe(
        metadata=RecipeMetadata(title=llm_out.title, servings=llm_out.servings, source_url=url),
        ingredients=llm_out.ingredients,
        steps=llm_out.steps,
        confidence=confidence,
        extraction_method=source,
    )
