"""
Turns raw trend/keyword signals into concrete, ready-to-film video topic
suggestions and full scripts using Groq.
"""

import os
import json
import re
import logging
from groq import Groq

log = logging.getLogger(__name__)


class TopicGenerationError(Exception):
    """Raised when the LLM call fails or returns something unusable."""
    pass


# Default to Llama 3.3 70B - Groq's best free tier model
DEFAULT_MODEL = "llama-3.3-70b-versatile"

PROMPT_TEMPLATE = """You are a YouTube content strategist helping a creator plan their next video.

Niche: {niche}

Here are trending/related search signals for this niche, with demand indicators:
{signals_text}

For each signal, generate ONE compelling YouTube video title/topic idea that a creator
in this niche could actually make. The title should be specific, clickable, and true to
what the video would contain (no clickbait that overpromises).

Make sure to:
1. Use VARIED title formats — not the same structure for every topic (no repeating "The Ultimate Guide to..." for multiple titles)
2. Mix formats like: how-to titles, question titles, list titles ("5 Reasons..."), story/hook titles ("Why I Switched to..."), controversy titles ("The Problem With...")
3. Make each title sound distinct and natural, like a real YouTube creator wrote it
4. Keep titles punchy and under 70 characters where possible

Each title must use a DIFFERENT format from the others. Avoid starting multiple titles with the same word or phrase.

Also write a one-sentence "angle" explaining why this topic could work right now,
referencing the demand signal briefly.

Respond ONLY with a valid JSON object. Do not include markdown formatting, code fences, or extra text.
Format:
{{
  "topics": [
    {{"source_query": "...", "title": "...", "angle": "..."}}
  ]
}}

Generate exactly {count} items in the "topics" array, one per signal, in the same order as given."""

SCRIPT_PROMPT_TEMPLATE = """You are an expert YouTube scriptwriter.
Video Title: {title}
Video Angle: {angle}

Write a complete, ready-to-film YouTube video script. It must be engaging, fast-paced, and retain viewer attention.
Respond ONLY with a valid JSON object matching this exact format:
{{
  "hook": "A compelling 10-15 second opening hook to stop the scroll",
  "intro": "The introduction section (2-3 sentences explaining what the viewer will learn)",
  "body": ["Step/Point 1 of the main content", "Step/Point 2 of the main content", "Step/Point 3 of the main content"],
  "outro": "The conclusion including a specific call to action (e.g., subscribe, comment, click a link)",
  "b_roll": ["Visual idea 1 to show on screen", "Visual idea 2 to show on screen", "Visual idea 3 to show on screen"]
}}"""


def _format_signals_for_prompt(signals):
    lines = []
    for s in signals:
        demand_bits = []
        if s.get("trend_interest"):
            demand_bits.append(f"trend interest {s['trend_interest']}/100")
        if s.get("video_count"):
            demand_bits.append(f"{s['video_count']} recent videos, avg {s['avg_views']:,} views")
        demand_str = ", ".join(demand_bits) if demand_bits else "low signal"
        lines.append(f'- "{s["query"]}" ({demand_str})')
    return "\n".join(lines)


def _extract_json(text):
    """Strip tags and markdown code fences, then extract JSON object."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text.strip()


def generate_topic_ideas(niche, signals, api_key, model_name=None):
    """Calls Groq to turn raw signals into topic ideas."""
    if not api_key:
        raise TopicGenerationError(
            "No Groq API key found. Add GROQ_API_KEY to your .env file. "
            "Get a free key at https://console.groq.com/keys"
        )

    if not signals:
        raise TopicGenerationError("No trend signals available to generate topics from.")

    if model_name is None:
        model_name = os.getenv("GROQ_MODEL", DEFAULT_MODEL)

    raw_text = ""
    try:
        client = Groq(api_key=api_key)
        prompt = PROMPT_TEMPLATE.format(
            niche=niche,
            signals_text=_format_signals_for_prompt(signals),
            count=len(signals),
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a JSON API. You respond ONLY with valid JSON objects. No markdown, no code fences, no explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            response_format={"type": "json_object"},
        )

        raw_content = response.choices[0].message.content
        log.info("LLM raw response (first 500 chars): %s", raw_content[:500] if raw_content else "<empty>")
        raw_text = _extract_json(raw_content)
        parsed = json.loads(raw_text)
        ideas = parsed.get("topics", [])

        if not ideas or not isinstance(ideas, list):
            raise TopicGenerationError("AI returned no usable topics. Please try again.")

    except json.JSONDecodeError as e:
        log.error("JSON parse failed. Extracted text: %s", raw_text[:1000] if raw_text else "<empty>")
        raise TopicGenerationError("AI returned a malformed response. Please try again.") from e
    except TopicGenerationError:
        raise
    except Exception as e:
        error_str = str(e).lower()
        if "api key" in error_str or "authentication" in error_str or "401" in error_str:
            raise TopicGenerationError("Groq API key was rejected. Double-check GROQ_API_KEY in your .env file.")
        if "quota" in error_str or "429" in error_str or "rate" in error_str:
            raise TopicGenerationError("Groq free tier rate limit hit. Wait a minute and try again.")
        if "model" in error_str and ("not found" in error_str or "does not exist" in error_str or "404" in error_str):
            raise TopicGenerationError(f"The configured Groq model '{model_name}' is not available.")
        raise TopicGenerationError(f"AI topic generation failed: {e}")

    merged = []
    for i, signal in enumerate(signals):
        idea = ideas[i] if i < len(ideas) else {}
        merged.append({
            "query":          signal["query"],
            "title":          idea.get("title", signal["query"].title()),
            "angle":          idea.get("angle", "Based on current search interest in this topic."),
            "trend_interest": signal["trend_interest"],
            "video_count":    signal["video_count"],
            "avg_views":      signal["avg_views"],
            "sample_titles":  signal["sample_titles"],
        })

    return merged


def generate_video_script(title, angle, api_key, model_name=None):
    """Generates a full video script and B-roll ideas for a given title/angle."""
    if not api_key:
        raise TopicGenerationError("Missing Groq API key for script generation.")
    
    if model_name is None:
        model_name = os.getenv("GROQ_MODEL", DEFAULT_MODEL)

    try:
        client = Groq(api_key=api_key)
        prompt = SCRIPT_PROMPT_TEMPLATE.format(title=title, angle=angle)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a JSON API. You respond ONLY with valid JSON objects."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        raw_text = _extract_json(response.choices[0].message.content)
        parsed = json.loads(raw_text)
        
        return {
            "hook": parsed.get("hook", ""),
            "intro": parsed.get("intro", ""),
            "body": parsed.get("body", []),
            "outro": parsed.get("outro", ""),
            "b_roll": parsed.get("b_roll", [])
        }

    except Exception as e:
        raise TopicGenerationError(f"Failed to generate script: {e}")